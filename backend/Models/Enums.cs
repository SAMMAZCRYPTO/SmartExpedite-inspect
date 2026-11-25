namespace InspectFlowBackend.Models;

public enum InspectionStatus
{
    Received,
    Scheduled,
    InProgress,
    Completed,
    Finalized
}

public enum InspectorStatus
{
    Active,
    Inactive,
    Suspended
}

public enum ReportType
{
    Flash,
    Interim,
    Final
}

public enum FindingType
{
    NonConformance,
    Observation,
    Recommendation
}

public enum ApprovalStatus
{
    Pending,
    Approved,
    Rejected
}
