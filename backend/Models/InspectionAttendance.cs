namespace InspectFlowBackend.Models;

public class InspectionAttendance
{
    public Guid Id { get; set; } = Guid.NewGuid();
    
    public Guid InspectionId { get; set; }
    public Inspection? Inspection { get; set; }

    public Guid InspectorId { get; set; }
    public Inspector? Inspector { get; set; }
    
    // Check-in/out timestamps
    public DateTimeOffset? CheckInTime { get; set; }
    public DateTimeOffset? CheckOutTime { get; set; }
    
    // Geo-location verification
    public double? CheckInLatitude { get; set; }
    public double? CheckInLongitude { get; set; }
    public double? CheckOutLatitude { get; set; }
    public double? CheckOutLongitude { get; set; }
    
    public bool LocationVerified { get; set; } = false;
    public decimal? DistanceFromSiteMeters { get; set; }
    
    // Notes
    public string? CheckInNotes { get; set; }
    public string? CheckOutNotes { get; set; }
    
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
}
