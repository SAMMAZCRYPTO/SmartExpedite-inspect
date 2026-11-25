namespace InspectFlowBackend.Models;

public class Inspector
{
    public Guid Id { get; set; } = Guid.NewGuid();
    
    // Represents mapping to Microsoft Entra ID or Auth system UUID
    public Guid? UserId { get; set; }
    
    public Guid? TpiAgencyId { get; set; }
    public TpiAgency? TpiAgency { get; set; }
    
    public string FullName { get; set; } = string.Empty;
    public string Email { get; set; } = string.Empty;
    public string? Phone { get; set; }
    
    // Stored as comma-separated or JSON array string
    public string? Specialization { get; set; }
    
    public string? Certifications { get; set; }
    public int? ExperienceYears { get; set; }
    public string? CvUrl { get; set; }
    public string? PhotoUrl { get; set; }
    
    public InspectorStatus Status { get; set; } = InspectorStatus.Active;
    
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset UpdatedAt { get; set; } = DateTimeOffset.UtcNow;
    
    // Navigation
    public ICollection<Inspection> Inspections { get; set; } = new List<Inspection>();
    public ICollection<InspectionReview> Reviews { get; set; } = new List<InspectionReview>();
    public ICollection<InspectionAttendance> Attendances { get; set; } = new List<InspectionAttendance>();
}
