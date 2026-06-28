package main

import "net/http"

// routes registers HTTP handlers. The cross-language resolver links the
// front-end client that calls these paths to this registrar.
func routes(mux *http.ServeMux) {
	mux.HandleFunc("/api/users/{id}", getUser)
	mux.HandleFunc("/api/health", health)
}

func getUser(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	writeJSON(w, lookup(id))
}

func health(w http.ResponseWriter, r *http.Request) {
	w.Write([]byte("ok"))
}

func lookup(id string) map[string]string {
	return map[string]string{"id": id}
}

func writeJSON(w http.ResponseWriter, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
}
