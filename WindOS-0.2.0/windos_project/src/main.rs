use eframe::egui::{self, Align, Color32, Layout, RichText, TextEdit, Vec2};
use windos::{authenticate, ADMIN_USERNAME};

const BG: Color32 = Color32::from_rgb(15, 23, 42);
const PANEL: Color32 = Color32::from_rgb(30, 41, 59);
const BLUE: Color32 = Color32::from_rgb(59, 130, 246);
const TEXT: Color32 = Color32::from_rgb(226, 232, 240);

struct WindOsApp {
    username: String,
    password: String,
    login_error: String,
    signed_in: bool,
    terminal_open: bool,
    files_open: bool,
    settings_open: bool,
    terminal_input: String,
    terminal_output: Vec<String>,
    gamemode: bool,
}

impl Default for WindOsApp {
    fn default() -> Self {
        Self {
            username: String::new(), password: String::new(), login_error: String::new(),
            signed_in: false, terminal_open: false, files_open: false, settings_open: false,
            terminal_input: String::new(),
            terminal_output: vec!["WindOS terminal — type 'help' to get started.".into()],
            gamemode: false,
        }
    }
}

impl WindOsApp {
    fn login(&mut self) {
        if authenticate(self.username.trim(), &self.password) {
            self.username = ADMIN_USERNAME.into();
            self.password.clear();
            self.login_error.clear();
            self.signed_in = true;
        } else {
            self.login_error = "That username or password was not recognized.".into();
        }
    }

    fn execute_command(&mut self) {
        let command = self.terminal_input.trim().to_ascii_lowercase();
        self.terminal_input.clear();
        if command.is_empty() { return; }
        self.terminal_output.push(format!("caleb@windos:~$ {command}"));
        let output = match command.as_str() {
            "help" => "Commands: help, windfetch, whoami, pwd, ls, winst help, gamemode on|off, clear, exit".into(),
            "whoami" => self.username.clone(),
            "pwd" => "/home/caleb".into(),
            "ls" | "dir" => "Desktop  Documents  Downloads  Games".into(),
            "windfetch" => format!("WindOS 0.2.0 (Breeze)\nUser: {}\nDesktop: WindOS Hybrid", self.username),
            "winst" | "winst help" => "winst — WindOS package manager\nTry: winst list | winst search <term> | sudo winst install <package>".into(),
            "gamemode" | "gamemode status" => format!("Game Mode is {}", if self.gamemode { "ON" } else { "OFF" }),
            "gamemode on" => { self.gamemode = true; "Game Mode enabled".into() },
            "gamemode off" => { self.gamemode = false; "Game Mode disabled".into() },
            "clear" => { self.terminal_output.clear(); return; },
            "exit" | "logout" => "Close the terminal window to return to the desktop.".into(),
            _ => format!("{command}: command not found (try 'help')"),
        };
        self.terminal_output.push(output);
    }

    fn show_login(&mut self, ctx: &egui::Context) {
        egui::CentralPanel::default().frame(egui::Frame::default().fill(BG)).show(ctx, |ui| {
            ui.vertical_centered(|ui| {
                ui.add_space((ui.available_height() * 0.18).max(0.0));
                ui.label(RichText::new("◈  WindOS").size(38.0).strong().color(Color32::WHITE));
                ui.add_space(8.0);
                ui.label(RichText::new("A familiar desktop, with a little Linux soul.").color(TEXT));
                ui.add_space(28.0);
                egui::Frame::group(ui.style()).fill(PANEL).show(ui, |ui| {
                    ui.set_width(340.0);
                    ui.heading("Welcome back");
                    ui.add_space(12.0);
                    ui.label("Username");
                    ui.add(TextEdit::singleline(&mut self.username).hint_text("Username").desired_width(320.0));
                    ui.add_space(8.0);
                    ui.label("Password");
                    let password = ui.add(TextEdit::singleline(&mut self.password).password(true).hint_text("Password").desired_width(320.0));
                    ui.add_space(14.0);
                    let sign_in = ui.add_sized([320.0, 38.0], egui::Button::new(RichText::new("Sign in").strong()).fill(BLUE));
                    if sign_in.clicked() || (password.lost_focus() && ui.input(|i| i.key_pressed(egui::Key::Enter))) { self.login(); }
                    if !self.login_error.is_empty() {
                        ui.add_space(8.0);
                        ui.label(RichText::new(&self.login_error).color(Color32::from_rgb(248, 113, 113)));
                    }
                });
                ui.add_space(14.0);
                ui.label(RichText::new("Private WindOS session · credentials are never displayed").small().color(Color32::GRAY));
            });
        });
    }

    fn show_desktop(&mut self, ctx: &egui::Context) {
        egui::TopBottomPanel::top("top_bar").frame(egui::Frame::default().fill(Color32::from_rgb(17, 26, 44))).show(ctx, |ui| {
            ui.horizontal(|ui| {
                ui.label(RichText::new("◈ WindOS").strong().color(Color32::WHITE));
                ui.separator();
                ui.label(RichText::new("Breeze Desktop").color(TEXT));
                ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                    if ui.button("⏻  Sign out").clicked() { self.signed_in = false; self.username.clear(); self.password.clear(); }
                    ui.label(RichText::new(format!("{}  ·  {}", self.username, if self.gamemode { "Game Mode" } else { "Ready" })).color(TEXT));
                });
            });
        });
        egui::TopBottomPanel::bottom("taskbar").frame(egui::Frame::default().fill(Color32::from_rgb(17, 26, 44))).show(ctx, |ui| {
            ui.horizontal(|ui| {
                if ui.add(egui::Button::new(RichText::new("⊞  Start").strong()).fill(BLUE)).clicked() { self.terminal_open = true; }
                ui.separator();
                if ui.button("▣  Terminal").clicked() { self.terminal_open = true; }
                if ui.button("▤  Files").clicked() { self.files_open = true; }
                if ui.button("⚙  Settings").clicked() { self.settings_open = true; }
                ui.with_layout(Layout::right_to_left(Align::Center), |ui| { ui.label(RichText::new("●  WindOS  ·  Breeze").color(TEXT)); });
            });
        });
        egui::SidePanel::left("launcher").resizable(false).default_width(176.0).frame(egui::Frame::default().fill(Color32::from_rgb(22, 33, 54))).show(ctx, |ui| {
            ui.add_space(12.0);
            ui.label(RichText::new("WORKSPACE").small().strong().color(Color32::from_rgb(148, 163, 184)));
            ui.add_space(8.0);
            ui.label("▦  Desktop");
            ui.add_space(12.0);
            ui.label(RichText::new("PINNED").small().strong().color(Color32::from_rgb(148, 163, 184)));
            ui.add_space(6.0);
            if ui.button("▣  Terminal").clicked() { self.terminal_open = true; }
            if ui.button("▤  File Explorer").clicked() { self.files_open = true; }
            if ui.button("⚙  Settings").clicked() { self.settings_open = true; }
            if ui.button("🎮  Game Mode").clicked() { self.gamemode = !self.gamemode; }
            ui.with_layout(Layout::bottom_up(Align::Min), |ui| { ui.label(RichText::new("WindOS 0.2 · Breeze").small().color(Color32::GRAY)); });
        });
        egui::CentralPanel::default().frame(egui::Frame::default().fill(BG)).show(ctx, |ui| {
            ui.vertical_centered(|ui| {
                ui.add_space(28.0);
                ui.label(RichText::new("Your desktop, your way.").size(28.0).strong().color(Color32::WHITE));
                ui.label(RichText::new("Windows-style ease. Linux-inspired control.").color(Color32::from_rgb(148, 163, 184)));
                ui.add_space(26.0);
                ui.horizontal_wrapped(|ui| {
                    if desktop_tile(ui, "▣", "Terminal", "Run WindOS commands") { self.terminal_open = true; }
                    if desktop_tile(ui, "▤", "Files", "Browse your workspace") { self.files_open = true; }
                    if desktop_tile(ui, "⚙", "Settings", "Personalize your system") { self.settings_open = true; }
                });
                ui.add_space(24.0);
                egui::Frame::group(ui.style()).fill(PANEL).show(ui, |ui| {
                    ui.set_width(440.0);
                    ui.horizontal(|ui| {
                        ui.label(RichText::new("●").color(if self.gamemode { Color32::GREEN } else { Color32::from_rgb(148, 163, 184) }));
                        ui.vertical(|ui| {
                            ui.label(RichText::new("System status").strong().color(TEXT));
                            ui.label(RichText::new(if self.gamemode { "Game Mode is on · 4 apps pinned" } else { "All systems ready · 4 apps pinned" }).small().color(Color32::LIGHT_GRAY));
                        });
                        ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                            if ui.button(if self.gamemode { "Turn off" } else { "Enable" }).clicked() { self.gamemode = !self.gamemode; }
                        });
                    });
                });
            });
        });
        self.show_windows(ctx);
    }

    fn show_windows(&mut self, ctx: &egui::Context) {
        let mut terminal_open = self.terminal_open;
        egui::Window::new("▣  Terminal").open(&mut terminal_open).default_size(Vec2::new(610.0, 390.0)).resizable(true).show(ctx, |ui| {
            egui::ScrollArea::vertical().stick_to_bottom(true).show(ui, |ui| {
                for line in &self.terminal_output { ui.label(RichText::new(line).monospace().color(TEXT)); }
            });
            ui.separator();
            ui.horizontal(|ui| {
                ui.label(RichText::new("❯").color(Color32::LIGHT_GREEN));
                let input = ui.add(TextEdit::singleline(&mut self.terminal_input).hint_text("Enter a command").desired_width(420.0));
                if input.lost_focus() && ui.input(|i| i.key_pressed(egui::Key::Enter)) { self.execute_command(); }
                if ui.button("Run").clicked() { self.execute_command(); }
            });
        });
        self.terminal_open = terminal_open;
        let mut files_open = self.files_open;
        egui::Window::new("▤  File Explorer").open(&mut files_open).default_size(Vec2::new(520.0, 360.0)).show(ctx, |ui| {
            ui.horizontal(|ui| {
                ui.label(RichText::new("Home  ›  caleb").color(Color32::LIGHT_BLUE));
                ui.with_layout(Layout::right_to_left(Align::Center), |ui| { ui.label("Search files  🔍"); });
            });
            ui.separator();
            for (icon, name) in [("▣", "Desktop"), ("▤", "Documents"), ("⬇", "Downloads"), ("🎮", "Games")] {
                ui.horizontal(|ui| {
                    ui.label(RichText::new(icon).size(20.0).color(Color32::LIGHT_BLUE));
                    ui.label(RichText::new(name).strong().color(TEXT));
                    ui.with_layout(Layout::right_to_left(Align::Center), |ui| { ui.label(RichText::new("Folder").small().color(Color32::GRAY)); });
                });
                ui.separator();
            }
            ui.label(RichText::new("This view represents the WindOS virtual home directory.").small().color(Color32::GRAY));
        });
        self.files_open = files_open;
        let mut settings_open = self.settings_open;
        egui::Window::new("⚙  Settings").open(&mut settings_open).default_size(Vec2::new(440.0, 300.0)).show(ctx, |ui| {
            ui.heading("Personalization");
            ui.label("Choose how your WindOS desktop behaves.");
            ui.separator();
            ui.horizontal(|ui| {
                ui.label("Game Mode");
                ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                    if ui.button(if self.gamemode { "On" } else { "Off" }).clicked() { self.gamemode = !self.gamemode; }
                });
            });
            ui.label("Pauses background activity in this emulated desktop.");
            ui.separator();
            ui.label(format!("Signed in as {}", self.username));
            ui.label("Theme: Midnight Breeze");
        });
        self.settings_open = settings_open;
    }
}

fn desktop_tile(ui: &mut egui::Ui, icon: &str, title: &str, subtitle: &str) -> bool {
    let mut clicked = false;
    egui::Frame::group(ui.style()).fill(PANEL).show(ui, |ui| {
        ui.set_min_size(Vec2::new(120.0, 105.0));
        ui.vertical_centered(|ui| {
            ui.label(RichText::new(icon).size(30.0).color(Color32::LIGHT_BLUE));
            if ui.button(RichText::new(title).strong().color(TEXT)).clicked() { clicked = true; }
            ui.label(RichText::new(subtitle).small().color(Color32::LIGHT_GRAY));
        });
    });
    clicked
}

impl eframe::App for WindOsApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        if self.signed_in { self.show_desktop(ctx); } else { self.show_login(ctx); }
    }
}

fn main() -> eframe::Result<()> {
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1100.0, 720.0])
            .with_min_inner_size([780.0, 540.0])
            .with_title("WindOS — Breeze Desktop"),
        ..Default::default()
    };
    eframe::run_native("WindOS — Breeze Desktop", options, Box::new(|_cc| Ok(Box::new(WindOsApp::default()))))
}
