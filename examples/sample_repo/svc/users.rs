// A third back-end, in Rust (axum), serving the same /api/users/{id} route.
// With this file the sample's TypeScript client fans out to handlers in three
// languages — Go, Python, and Rust — none of which it references by name.

use axum::{routing::get, Router};

pub fn router() -> Router {
    Router::new()
        .route("/api/users/{id}", get(get_user))
        .route("/api/health", get(health))
}

async fn get_user() -> String {
    lookup("id")
}

async fn health() -> &'static str {
    "ok"
}

fn lookup(id: &str) -> String {
    normalize(id)
}

fn normalize(value: &str) -> String {
    value.trim().to_string()
}
