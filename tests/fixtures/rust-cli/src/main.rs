use clap::Parser;

#[derive(Parser)]
struct Cli {
    /// Overwrite existing files.
    #[arg(long)]
    force: bool,
    #[arg(long, env = "RCLI_CONFIG")]
    config: Option<String>,
}

fn main() {
    let _ = std::env::var("RCLI_CACHE_DIR");
    let _ = Cli::parse();
}
