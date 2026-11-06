use std::io::{self, Write};
use windos::{authenticate, default_user, ADMIN_PASSWORD, ADMIN_USERNAME};

fn prompt(label: &str) -> String {
    print!("{label}");
    io::stdout().flush().expect("failed to flush stdout");

    let mut value = String::new();
    io::stdin()
        .read_line(&mut value)
        .expect("failed to read input");
    value.trim().to_string()
}

fn run_shell() {
    let user = default_user();
    let mut gamemode = false;
    println!("\nWelcome back, {}. Type 'help' for commands.", user.username);

    loop {
        let command = prompt(&format!("{}@windos:~$ ", user.username));
        if command.is_empty() {
            continue;
        }

        match command.as_str() {
            "help" => {
                println!("Available commands:");
                println!("  help      Show this help menu");
                println!("  wind      Open the WindOS hub");
                println!("  winst     Package manager");
                println!("  gamemode  Toggle performance tuning");
                println!("  exit      Leave the shell");
            }
            "wind" => {
                println!("WindOS hub: desktop, system panel, package manager, and quick launch");
            }
            "winst" => {
                println!("winst: package manager ready for update, install, and rollback operations");
            }
            "gamemode" | "gamemode on" => {
                gamemode = true;
                println!("Game Mode enabled");
            }
            "gamemode off" => {
                gamemode = false;
                println!("Game Mode disabled");
            }
            "exit" | "logout" | "quit" => break,
            _ => println!("Command not recognized: {}", command),
        }
    }

    println!("\nSession closed. Game Mode {}.", if gamemode { "enabled" } else { "disabled" });
}

fn main() {
    println!("WindOS 0.2.0 (Breeze)");

    let username = prompt("Username: ");
    let password = prompt("Password: ");

    if !authenticate(&username, &password) {
        eprintln!("Authentication failed.");
        std::process::exit(1);
    }

    println!("Login successful for {}.", ADMIN_USERNAME);
    println!("Default admin password is set to: {}", ADMIN_PASSWORD);
    run_shell();
}
