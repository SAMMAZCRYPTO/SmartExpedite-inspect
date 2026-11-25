namespace InspectFlowBackend.Models;

public class InspectionReview
{
    public Guid Id { get; set; } = Guid.NewGuid();
    
    // Foreign Keys
    public Guid InspectionId { get; set; }
    public Inspection? Inspection { get; set; }

    public Guid InspectorId { get; set; }
    public Inspector? Inspector { get; set; }

    public Guid? ReviewedBy { get; set; } // Microsoft Entra ID Reviewer Reference
    
    // Review scores (0-100)
    public int? ReportQualityScore { get; set; }
    public int? TimelinessScore { get; set; }
    public int? CommunicationScore { get; set; }
    public int? OverallScore { get; set; }
    
    // Performance metrics
    public int MissedNcrCount { get; set; } = 0;
    public int FalseNcrCount { get; set; } = 0;
    
    // Comments
    public string? Strengths { get; set; }
    public string? AreasForImprovement { get; set; }
    public string? AdditionalComments { get; set; }
    
    public DateTimeOffset ReviewDate { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
}
