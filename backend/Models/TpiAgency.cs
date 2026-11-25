namespace InspectFlowBackend.Models;

public class TpiAgency
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public string Name { get; set; } = string.Empty;
    public string? CompanyCode { get; set; }
    public string? ManagerName { get; set; }
    public string? ManagerEmail { get; set; }
    public string? ManagerPhone { get; set; }
    public string? Address { get; set; }
    public string? City { get; set; }
    public string? Country { get; set; }
    
    // JSON mapping (EF Core JSON support)
    public string? CertificationInfo { get; set; }
    
    public string Status { get; set; } = "active";
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset UpdatedAt { get; set; } = DateTimeOffset.UtcNow;
    
    // Navigation
    public ICollection<Inspector> Inspectors { get; set; } = new List<Inspector>();
    public ICollection<Inspection> Inspections { get; set; } = new List<Inspection>();
}
