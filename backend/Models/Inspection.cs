namespace InspectFlowBackend.Models;

public class Inspection
{
    public Guid Id { get; set; } = Guid.NewGuid();
    
    // Basic Information
    public string PoNumber { get; set; } = string.Empty;
    public string NotificationNumber { get; set; } = string.Empty;
    public string? NotificationRevision { get; set; }
    public string SupplierName { get; set; } = string.Empty;
    public string? SubsupplierName { get; set; }
    public string? SupplierAddress { get; set; }
    public string? Country { get; set; }
    
    public string? PoDescription { get; set; }
    public string? InspectionType { get; set; }
    
    // Vendor Contact Info
    public string? VendorContactName { get; set; }
    public string? VendorContactPhone { get; set; }
    public string? VendorContactEmail { get; set; }
    
    // Foreign Keys
    public Guid? ProjectId { get; set; }
    public Project? Project { get; set; }

    public Guid? AssignedInspectorId { get; set; }
    public Inspector? Inspector { get; set; }

    public Guid? TpiAgencyId { get; set; }
    public TpiAgency? TpiAgency { get; set; }

    public Guid? AssignedBy { get; set; } // Microsoft Entra ID QC Manager Reference
    
    // Dates
    public DateTime? NotificationDate { get; set; }
    public DateTime? NotificationReceiptDate { get; set; }
    public DateTime? StartDate { get; set; }
    public DateTime? EndDate { get; set; }
    public DateTime? ExpectedCompletionDate { get; set; }
    public DateTime? ActualCompletionDate { get; set; }
    public string? AllInspectionDates { get; set; }
    public string? InspectionTime { get; set; }
    
    // Location
    public string? LocationName { get; set; }
    public string? LocationAddress { get; set; }
    
    // Spatial abstraction
    public double? LocationLatitude { get; set; }
    public double? LocationLongitude { get; set; }
    
    public InspectionStatus Status { get; set; } = InspectionStatus.Received;
    public string? CreatedBy { get; set; }
    
    // JSON Structured Objects (Mapped as string or owned types in EF Core)
    public string? ItemsBeingOffered { get; set; }
    public string? InspectionReports { get; set; }
    public string? InspectionActivities { get; set; }
    public string? Notes { get; set; }
    
    public string? ReleaseNoteUrl { get; set; }
    
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset UpdatedAt { get; set; } = DateTimeOffset.UtcNow;
    
    // Navigations
    public ICollection<InspectionReview> Reviews { get; set; } = new List<InspectionReview>();
    public ICollection<InspectionAttendance> Attendances { get; set; } = new List<InspectionAttendance>();
}
