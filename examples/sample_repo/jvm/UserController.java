package com.acme;

import org.springframework.web.bind.annotation.*;

// A Spring back-end serving the same /api/users/{id} route. The route lives in
// a @GetMapping annotation, which the extractor attaches to the method below.
@RestController
public class UserController {

    @GetMapping("/api/users/{id}")
    public User getUser(@PathVariable String id) {
        return lookup(id);
    }

    @GetMapping("/api/health")
    public String health() {
        return "ok";
    }

    private User lookup(String id) {
        return new User(id);
    }
}
