using Microsoft.AspNetCore.Mvc;

namespace Acme;

// An ASP.NET back-end serving the same /api/users/{id} route. The route lives
// in an [HttpGet] attribute, attached to the method that follows it.
public class UsersController : ControllerBase
{
    [HttpGet("/api/users/{id}")]
    public User GetUser(string id)
    {
        return Lookup(id);
    }

    [HttpGet("/api/health")]
    public string Health()
    {
        return "ok";
    }

    private User Lookup(string id)
    {
        return new User(id);
    }
}
