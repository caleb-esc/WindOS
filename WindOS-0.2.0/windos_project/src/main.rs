use eframe::egui::{self, Align, Color32, Layout, RichText, TextEdit, Vec2};
use std::{fs, path::{Component, Path, PathBuf}};
use windos::{authenticate, catalog, install_package, load_package_state, remove_package, save_package_state, PackageState, ADMIN_USERNAME};

const BG: Color32 = Color32::from_rgb(12, 18, 32);
const PANEL: Color32 = Color32::from_rgb(25, 36, 56);
const BLUE: Color32 = Color32::from_rgb(59, 130, 246);
const TEXT: Color32 = Color32::from_rgb(226, 232, 240);

struct WindOsApp {
    username: String, password: String, login_error: String, signed_in: bool,
    terminal_open: bool, files_open: bool, settings_open: bool, store_open: bool,
    terminal_input: String, terminal_output: Vec<String>, gamemode: bool,
    package_state: PackageState, current_dir: String, file_error: String,
    new_file: String, sudo_pending: Option<String>, sudo_password: String,
    sudo_error: String, show_start: bool,
}

impl Default for WindOsApp {
    fn default() -> Self {
        Self {
            username:String::new(), password:String::new(), login_error:String::new(), signed_in:false,
            terminal_open:false, files_open:false, settings_open:false, store_open:false,
            terminal_input:String::new(), terminal_output:vec!["WindOS terminal — type 'help' to get started.".into()],
            gamemode:false, package_state:load_package_state(), current_dir:"/home/caleb".into(),
            file_error:String::new(), new_file:String::new(), sudo_pending:None,
            sudo_password:String::new(), sudo_error:String::new(), show_start:false,
        }
    }
}

impl WindOsApp {
    fn login(&mut self) {
        if authenticate(self.username.trim(), &self.password) {
            self.username=ADMIN_USERNAME.into(); self.password.clear(); self.login_error.clear(); self.signed_in=true;
        } else { self.login_error="That username or password was not recognized.".into(); }
    }
    fn root() -> PathBuf {
        std::env::var_os("WINDOS_ROOT").map(PathBuf::from)
            .or_else(|| std::env::var_os("USERPROFILE").map(|p|PathBuf::from(p).join(".windos")))
            .or_else(|| std::env::var_os("HOME").map(|p|PathBuf::from(p).join(".windos")))
            .unwrap_or_else(||PathBuf::from(".windos"))
    }
    fn virtual_path(&self, input: &str) -> Result<PathBuf,String> {
        let mut parts: Vec<String> = if input.starts_with('/') { Vec::new() } else {
            self.current_dir.split('/').filter(|s|!s.is_empty()).map(str::to_string).collect()
        };
        for c in Path::new(input).components() {
            match c {
                Component::RootDir | Component::CurDir => {},
                Component::ParentDir => { parts.pop(); },
                Component::Normal(n) => parts.push(n.to_string_lossy().to_string()),
                Component::Prefix(_) => return Err("host paths are not available in the virtual filesystem".into()),
            }
        }
        let root=Self::root();
        let result=parts.iter().fold(root.clone(),|p,s|p.join(s));
        // Reject symlinks that would escape the sandbox when the target exists.
        if let (Ok(real_root),Ok(real_target))=(root.canonicalize(),result.canonicalize()) {
            if !real_target.starts_with(real_root) { return Err("path escapes the WindOS virtual root".into()); }
        }
        Ok(result)
    }
    fn run_command(&mut self, line: &str) -> String {
        let line=line.trim();
        if line.is_empty(){return String::new();}
        if line.split(';').count()>1 { return "Command chaining is not supported.".into(); }
        let args:Vec<&str>=line.split_whitespace().collect();
        if args.is_empty(){return String::new();}
        let (sudo,offset)=if args[0]=="sudo" {(true,1)} else {(false,0)};
        if offset>=args.len(){return "Usage: sudo <command>".into();}
        let cmd=args[offset]; let rest=&args[offset+1..];
        if sudo && cmd=="winst" {
            if rest.is_empty(){return winst_help();}
            match rest[0] {
                "help"|"--help"=>winst_help(),
                "list"=>self.winst_list(false),
                "search"=>self.winst_search(&rest[1..]),
                "info"=>self.winst_info(rest.get(1).copied()),
                "history"=>if self.package_state.history.is_empty(){"No package transactions yet.".into()}else{self.package_state.history.join("\n")},
                "install"|"remove"|"purge"|"update"|"upgrade"|"autoremove"|"clean"=>{
                    self.sudo_pending=Some(line.to_string()); self.sudo_password.clear(); self.sudo_error.clear();
                    "Sudo authentication required. Confirm the command in the authentication dialog.".into()
                }
                _=>format!("winst: invalid operation '{}'. Try 'winst help'.",rest[0]),
            }
        } else if sudo {
            "sudo is currently limited to the emulated winst package manager.".into()
        } else { self.run_unprivileged(cmd,rest) }
    }
    fn run_unprivileged(&mut self, cmd:&str, args:&[&str])->String {
        match cmd {
            "help"=>"Commands: help, windfetch, whoami, pwd, ls [path], cd <path>, cat <file>, mkdir <name>, touch <file>, gamemode on|off|status, winst <command>, sudo winst <install|remove|update|upgrade|...>, clear, exit".into(),
            "whoami"=>self.username.clone(), "pwd"=>self.current_dir.clone(),
            "windfetch"=>format!("WindOS 0.2.0 (Breeze)\nUser: {}\nInstalled packages: {}\nGame Mode: {}",self.username,self.package_state.installed.len(),if self.gamemode{"ON"}else{"OFF"}),
            "ls"|"dir"=>{let path=args.first().copied().unwrap_or(".");match self.virtual_path(path){Ok(p)=>match fs::read_dir(p){Ok(entries)=>{let mut names:Vec<String>=entries.filter_map(Result::ok).map(|e|{let n=e.file_name().to_string_lossy().to_string();if e.path().is_dir(){format!("{n}/")}else{n}}).collect();names.sort();if names.is_empty(){"(empty)".into()}else{names.join("  ")}},Err(e)=>format!("ls: {e}")},Err(e)=>e}},
            "cd"=>{let target=args.first().copied().unwrap_or("/home/caleb");match self.virtual_path(target){Ok(p) if p.is_dir()=>{self.current_dir=virtual_display(&Self::root(),&p);self.current_dir.clone()},Ok(_)=>"cd: not a directory".into(),Err(e)=>e}},
            "cat"|"type"=>match args.first(){Some(name)=>match self.virtual_path(name){Ok(p)=>fs::read_to_string(p).unwrap_or_else(|e|format!("cat: {e}")),Err(e)=>e},None=>"Usage: cat <file>".into()},
            "mkdir"=>self.file_command(args.first().copied(),true), "touch"=>self.touch_command(args.first().copied()),
            "gamemode"=>match args.first().copied().unwrap_or("status"){"on"=>{self.gamemode=true;"Game Mode enabled".into()},"off"=>{self.gamemode=false;"Game Mode disabled".into()},_=>format!("Game Mode is {}",if self.gamemode{"ON"}else{"OFF"})},
            "winst"=>if args.is_empty(){winst_help()}else{match args[0]{"list"=>self.winst_list(false),"search"=>self.winst_search(&args[1..]),"info"=>self.winst_info(args.get(1).copied()),"history"=>self.package_state.history.join("\n"),"help"=>winst_help(),_=>"System changes require sudo: sudo winst install/remove/update/upgrade".into()}},
            "clear"=>{self.terminal_output.clear();String::new()}, "exit"|"logout"=>"Use the Sign out button to end your session.".into(),
            _=>format!("{cmd}: command not found (try 'help')"),
        }
    }
    fn file_command(&self,name:Option<&str>,directory:bool)->String {
        let Some(name)=name else{return "Usage: mkdir <directory>".into()};
        match self.virtual_path(name){Ok(p)=>{let r=if directory{fs::create_dir_all(p)}else{fs::write(p,b"")};r.map(|_|format!("Created {name}")).unwrap_or_else(|e|format!("{e}"))},Err(e)=>e}
    }
    fn touch_command(&self,name:Option<&str>)->String {
        let Some(name)=name else{return "Usage: touch <file>".into()};
        match self.virtual_path(name){Ok(p)=>{if let Some(parent)=p.parent(){if let Err(e)=fs::create_dir_all(parent){return e.to_string();}}fs::OpenOptions::new().create(true).append(true).open(p).map(|_|format!("Touched {name}")).unwrap_or_else(|e|e.to_string())},Err(e)=>e}
    }
    fn winst_list(&self,installed_only:bool)->String {
        let mut out=String::from("PACKAGE       VERSION  STATUS      DESCRIPTION\n");
        for p in catalog(){let installed=self.package_state.installed.get(&p.name);if installed_only&&installed.is_none(){continue;}out.push_str(&format!("{:<14}{:<9}{:<12}{}\n",p.name,installed.unwrap_or(&p.version),if installed.is_some(){"installed"}else{"available"},p.description));}
        out
    }
    fn winst_search(&self,terms:&[&str])->String {
        if terms.is_empty(){return "Usage: winst search <term>".into();}
        let q=terms.join(" ").to_lowercase();let hits:Vec<String>=catalog().into_iter().filter(|p|format!("{} {} {}",p.name,p.description,p.category).to_lowercase().contains(&q)).map(|p|format!("{}/{} — {}",p.name,p.version,p.description)).collect();
        if hits.is_empty(){format!("No packages found for '{q}'.")}else{hits.join("\n")}
    }
    fn winst_info(&self,name:Option<&str>)->String {
        let Some(name)=name else{return "Usage: winst info <package>".into()};
        catalog().into_iter().find(|p|p.name==name).map(|p|format!("Package: {}\nVersion: {}\nCategory: {}\nSize: {} kB\nStatus: {}\nDescription: {}",p.name,p.version,p.category,p.size_kb,if self.package_state.installed.contains_key(name){"installed"}else{"available"},p.description)).unwrap_or_else(||format!("Unable to locate package '{name}'."))
    }
    fn confirm_sudo(&mut self) {
        let Some(command)=self.sudo_pending.take() else{return};
        if !authenticate(&self.username,&self.sudo_password){self.sudo_error="Authentication failed.".into();self.sudo_pending=Some(command);return;}
        self.sudo_password.clear();
        let args:Vec<&str>=command.split_whitespace().collect();let verb=args.get(2).copied().unwrap_or("");let names=&args[3..];
        let result=match verb {
            "install"=>if names.is_empty(){"Usage: sudo winst install <package>".into()}else{names.iter().map(|n|install_package(&mut self.package_state,n).unwrap_or_else(|e|e)).collect::<Vec<_>>().join("\n")},
            "remove"|"purge"=>if names.is_empty(){"Usage: sudo winst remove <package>".into()}else{names.iter().map(|n|remove_package(&mut self.package_state,n).unwrap_or_else(|e|e)).collect::<Vec<_>>().join("\n")},
            "update"=>{self.package_state.revision+=1;let r=save_package_state(&self.package_state);format!("Package index refreshed (revision {}).{}",self.package_state.revision,r.err().map(|e|format!(" Save failed: {e}")).unwrap_or_default())},
            "upgrade"=>"All installed packages are at their latest available versions.".into(),
            "autoremove"=>"No unused packages to remove.".into(),
            "clean"=>"Package cache is empty.".into(),
            _=>"Unsupported sudo winst operation.".into(),
        };
        self.terminal_output.push(result);
    }
    fn refresh_files(&mut self) { self.file_error.clear(); }
    fn show_login(&mut self,ctx:&egui::Context) {
        egui::CentralPanel::default().frame(egui::Frame::default().fill(BG)).show(ctx,|ui|{ui.vertical_centered(|ui|{ui.add_space((ui.available_height()*0.16).max(0.0));ui.label(RichText::new("◈  WindOS").size(42.0).strong().color(Color32::WHITE));ui.label(RichText::new("A familiar desktop, with a little Linux soul.").color(TEXT));ui.add_space(26.0);egui::Frame::group(ui.style()).fill(PANEL).show(ui,|ui|{ui.set_width(360.0);ui.heading("Welcome back");ui.add_space(12.0);ui.label("Username");ui.add(TextEdit::singleline(&mut self.username).hint_text("Username").desired_width(330.0));ui.add_space(8.0);ui.label("Password");let pw=ui.add(TextEdit::singleline(&mut self.password).password(true).hint_text("Password").desired_width(330.0));ui.add_space(12.0);let b=ui.add_sized([330.0,40.0],egui::Button::new("Sign in").fill(BLUE));if b.clicked()||(pw.lost_focus()&&ui.input(|i|i.key_pressed(egui::Key::Enter))){self.login();}if !self.login_error.is_empty(){ui.colored_label(Color32::LIGHT_RED,&self.login_error);}});});});
    }
    fn show_desktop(&mut self,ctx:&egui::Context) {
        egui::TopBottomPanel::top("top").frame(egui::Frame::default().fill(Color32::from_rgb(17,26,44))).show(ctx,|ui|{ui.horizontal(|ui|{ui.label(RichText::new("◈ WindOS").strong().color(Color32::WHITE));ui.separator();ui.label("Breeze Desktop");ui.with_layout(Layout::right_to_left(Align::Center),|ui|{if ui.button("⏻ Sign out").clicked(){self.signed_in=false;self.username.clear();}ui.label(format!("{} · {}",self.username,if self.gamemode{"Game Mode"}else{"Ready"}));});});});
        egui::TopBottomPanel::bottom("taskbar").frame(egui::Frame::default().fill(Color32::from_rgb(17,26,44))).show(ctx,|ui|{ui.horizontal(|ui|{if ui.add(egui::Button::new("⊞ Start").fill(BLUE)).clicked(){self.show_start=!self.show_start;}ui.separator();if ui.button("▣ Terminal").clicked(){self.terminal_open=true;}if ui.button("▤ Files").clicked(){self.files_open=true;}if ui.button("🛍 Store").clicked(){self.store_open=true;}if ui.button("⚙ Settings").clicked(){self.settings_open=true;}ui.with_layout(Layout::right_to_left(Align::Center),|ui|{ui.label("● WindOS · Breeze");});});});
        egui::SidePanel::left("launcher").resizable(false).default_width(180.0).frame(egui::Frame::default().fill(Color32::from_rgb(22,33,54))).show(ctx,|ui|{ui.add_space(12.0);ui.label(RichText::new("WORKSPACE").small().strong().color(Color32::GRAY));ui.add_space(8.0);ui.label("▦  Desktop");ui.separator();ui.label(RichText::new("PINNED APPS").small().strong().color(Color32::GRAY));if ui.button("▣  Terminal").clicked(){self.terminal_open=true;}if ui.button("▤  File Explorer").clicked(){self.files_open=true;}if ui.button("🛍  Software Store").clicked(){self.store_open=true;}if ui.button("⚙  Settings").clicked(){self.settings_open=true;}if ui.button("🎮  Toggle Game Mode").clicked(){self.gamemode=!self.gamemode;}});
        egui::CentralPanel::default().frame(egui::Frame::default().fill(BG)).show(ctx,|ui|{ui.vertical_centered(|ui|{ui.add_space(30.0);ui.label(RichText::new("Your desktop, your way.").size(30.0).strong().color(Color32::WHITE));ui.label(RichText::new("Windows-style ease. Linux-inspired control.").color(Color32::GRAY));ui.add_space(25.0);ui.horizontal_wrapped(|ui|{if tile(ui,"▣","Terminal","Commands & sudo winst"){self.terminal_open=true;}if tile(ui,"▤","File Explorer","Browse virtual files"){self.files_open=true;}if tile(ui,"🛍","Software Store","Discover packages"){self.store_open=true;}if tile(ui,"⚙","Settings","Desktop preferences"){self.settings_open=true;}});ui.add_space(20.0);egui::Frame::group(ui.style()).fill(PANEL).show(ui,|ui|{ui.set_width(500.0);ui.horizontal(|ui|{ui.label(if self.gamemode{"🟢"}else{"●"});ui.vertical(|ui|{ui.label(RichText::new("System overview").strong());ui.label(format!("{} installed packages · Game Mode {}",self.package_state.installed.len(),if self.gamemode{"ON"}else{"OFF"}));});ui.with_layout(Layout::right_to_left(Align::Center),|ui|{if ui.button("Open Store").clicked(){self.store_open=true;}});});});});});
        self.show_windows(ctx);
        if self.show_start {egui::Window::new("Start").collapsible(false).resizable(false).default_pos([24.0,330.0]).show(ctx,|ui|{ui.heading("Pinned");if ui.button("Terminal").clicked(){self.terminal_open=true;self.show_start=false;}if ui.button("File Explorer").clicked(){self.files_open=true;self.show_start=false;}if ui.button("Software Store").clicked(){self.store_open=true;self.show_start=false;}if ui.button("Settings").clicked(){self.settings_open=true;self.show_start=false;}});}
    }
    fn show_windows(&mut self,ctx:&egui::Context) {
        let mut open=self.terminal_open;egui::Window::new("▣ Terminal").open(&mut open).default_size([660.0,430.0]).show(ctx,|ui|{ui.horizontal(|ui|{ui.label(RichText::new("caleb@windos").color(Color32::LIGHT_GREEN));ui.label(format!("{}$",self.current_dir));});ui.separator();egui::ScrollArea::vertical().stick_to_bottom(true).max_height(320.0).show(ui,|ui|{for row in &self.terminal_output{ui.label(RichText::new(row).monospace().color(TEXT));}});ui.separator();ui.horizontal(|ui|{let entry=ui.add(TextEdit::singleline(&mut self.terminal_input).hint_text("help · winst search games · sudo winst install raceline").desired_width(485.0));let run=ui.button("Run");if run.clicked()||(entry.lost_focus()&&ui.input(|i|i.key_pressed(egui::Key::Enter))){let cmd=std::mem::take(&mut self.terminal_input);self.terminal_output.push(format!("{}@windos:{}$ {}",self.username,self.current_dir,cmd));let out=self.run_command(&cmd);if !out.is_empty(){self.terminal_output.push(out);}}});});self.terminal_open=open;
        let mut open=self.files_open;egui::Window::new("▤ File Explorer").open(&mut open).default_size([620.0,430.0]).show(ctx,|ui|{ui.horizontal(|ui|{if ui.button("⌂ Home").clicked(){self.current_dir="/home/caleb".into();}if ui.button("↑ Up").clicked(){if let Some((parent,_))=self.current_dir.rsplit_once('/') {self.current_dir=if parent.is_empty(){"/".into()}else{parent.into()};}}ui.label(RichText::new(&self.current_dir).color(Color32::LIGHT_BLUE));});ui.separator();match self.virtual_path("."){Ok(dir)=>match fs::read_dir(dir){Ok(entries)=>{let mut rows:Vec<_>=entries.filter_map(Result::ok).collect();rows.sort_by_key(|e|(!e.path().is_dir(),e.file_name()));egui::ScrollArea::vertical().max_height(275.0).show(ui,|ui|{for e in rows{let name=e.file_name().to_string_lossy().to_string();ui.horizontal(|ui|{let label=if e.path().is_dir(){format!("📁  {name}")}else{format!("📄  {name}")};if ui.selectable_label(false,label).double_clicked()&&e.path().is_dir(){self.current_dir=format!("{}/{}",self.current_dir.trim_end_matches('/'),name);}if !e.path().is_dir()&&ui.small_button("Open").clicked(){match fs::read_to_string(e.path()){Ok(text)=>self.file_error=format!("{name}: {}",text.lines().take(6).collect::<Vec<_>>().join(" | ")),Err(err)=>self.file_error=err.to_string()}}});}});},Err(e)=>self.file_error=e.to_string()},Err(e)=>self.file_error=e};ui.separator();ui.horizontal(|ui|{ui.add(TextEdit::singleline(&mut self.new_file).hint_text("New file or folder name").desired_width(270.0));if ui.button("New file").clicked()&&!self.new_file.trim().is_empty(){let name=std::mem::take(&mut self.new_file);self.file_error=self.touch_command(Some(&name));}if ui.button("New folder").clicked()&&!self.new_file.trim().is_empty(){let name=std::mem::take(&mut self.new_file);self.file_error=self.file_command(Some(&name),true);}});if !self.file_error.is_empty(){ui.label(RichText::new(&self.file_error).small().color(Color32::LIGHT_BLUE));}});self.files_open=open;
        let mut open=self.store_open;egui::Window::new("🛍 Software Store — winst").open(&mut open).default_size([690.0,500.0]).show(ctx,|ui|{ui.horizontal(|ui|{ui.heading("Software");ui.with_layout(Layout::right_to_left(Align::Center),|ui|{if ui.button("⟳ Update index (sudo)").clicked(){self.run_command("sudo winst update");}});});ui.label("Browse the WindOS package catalog. Changes require sudo authentication.");ui.separator();ui.horizontal(|ui|{ui.label("Search");let mut query=String::new();ui.add(TextEdit::singleline(&mut query).hint_text("Package name or description").desired_width(260.0));if !query.is_empty(){ui.label(self.winst_search(&[&query]));}});egui::ScrollArea::vertical().max_height(360.0).show(ui,|ui|{for p in catalog(){ui.horizontal(|ui|{ui.vertical(|ui|{ui.label(RichText::new(format!("{}  {}",p.name,p.version)).strong().color(TEXT));ui.label(RichText::new(format!("{} · {} kB · {}",p.description,p.size_kb,p.category)).small().color(Color32::GRAY));});ui.with_layout(Layout::right_to_left(Align::Center),|ui|{if self.package_state.installed.contains_key(&p.name){if ui.button("Remove").clicked(){self.run_command(&format!("sudo winst remove {}",p.name));}}else if ui.button("Install").clicked(){self.run_command(&format!("sudo winst install {}",p.name));}});});ui.separator();}});ui.label(format!("{} packages installed",self.package_state.installed.len()));});self.store_open=open;
        let mut open=self.settings_open;egui::Window::new("⚙ Settings").open(&mut open).default_size([460.0,340.0]).show(ctx,|ui|{ui.heading("Personalization");ui.label("Make WindOS feel like home.");ui.separator();ui.horizontal(|ui|{ui.label("Dark Midnight Breeze theme");ui.with_layout(Layout::right_to_left(Align::Center),|ui|{ui.colored_label(Color32::LIGHT_GREEN,"Active");});});ui.separator();ui.horizontal(|ui|{ui.label("Game Mode");ui.with_layout(Layout::right_to_left(Align::Center),|ui|{if ui.checkbox(&mut self.gamemode,"Enabled").changed(){}});});ui.label("Emulated setting: pauses simulated background activity.");ui.separator();ui.label(format!("Account: {} · administrator",self.username));ui.label(format!("Virtual root: {}",Self::root().display()));});self.settings_open=open;
        if self.sudo_pending.is_some(){let mut keep=true;egui::Window::new("Administrator authentication").collapsible(false).resizable(false).open(&mut keep).show(ctx,|ui|{ui.label("Enter your WindOS password to authorize this emulated package operation.");if let Some(cmd)=&self.sudo_pending{ui.label(RichText::new(cmd).monospace().color(Color32::LIGHT_BLUE));}let pw=ui.add(TextEdit::singleline(&mut self.sudo_password).password(true).hint_text("Password").desired_width(300.0));ui.horizontal(|ui|{if ui.button("Authorize").clicked()||(pw.lost_focus()&&ui.input(|i|i.key_pressed(egui::Key::Enter))){self.confirm_sudo();}if ui.button("Cancel").clicked(){self.sudo_pending=None;self.sudo_password.clear();}});if !self.sudo_error.is_empty(){ui.colored_label(Color32::LIGHT_RED,&self.sudo_error);}});if !keep{self.sudo_pending=None;self.sudo_password.clear();}}
    }
}
fn tile(ui:&mut egui::Ui,icon:&str,title:&str,subtitle:&str)->bool{let mut clicked=false;egui::Frame::group(ui.style()).fill(PANEL).show(ui,|ui|{ui.set_min_size(Vec2::new(145.0,120.0));ui.vertical_centered(|ui|{ui.label(RichText::new(icon).size(28.0).color(Color32::LIGHT_BLUE));if ui.button(RichText::new(title).strong()).clicked(){clicked=true;}ui.label(RichText::new(subtitle).small().color(Color32::GRAY));});});clicked}
fn virtual_display(root:&Path,path:&Path)->String{path.strip_prefix(root).map(|r|format!("/{}",r.to_string_lossy().replace('\\',"/"))).unwrap_or_else(|_|"/".into())}
fn winst_help()->String{"winst — WindOS package manager\n  winst list [--installed] | search <term> | info <pkg> | history\n  sudo winst install <pkg> | remove <pkg> | update | upgrade | autoremove | clean".into()}

impl eframe::App for WindOsApp {fn update(&mut self,ctx:&egui::Context,_frame:&mut eframe::Frame){if self.signed_in{self.show_desktop(ctx)}else{self.show_login(ctx)}}}
fn main()->eframe::Result<()>{let options=eframe::NativeOptions{viewport:egui::ViewportBuilder::default().with_inner_size([1120.0,760.0]).with_min_inner_size([800.0,580.0]).with_title("WindOS — Breeze Desktop"),..Default::default()};eframe::run_native("WindOS — Breeze Desktop",options,Box::new(|_cc|Ok(Box::new(WindOsApp::default()))))}
