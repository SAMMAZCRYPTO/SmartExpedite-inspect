using InspectFlowBackend.Data;
using InspectFlowBackend.Models;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace InspectFlowBackend.Controllers;

[ApiController]
[Route("api/[controller]")]
public class InspectionsController : ControllerBase
{
    private readonly ApplicationDbContext _context;

    public InspectionsController(ApplicationDbContext context)
    {
        _context = context;
    }

    [HttpGet]
    public async Task<ActionResult<IEnumerable<Inspection>>> GetInspections()
    {
        var inspections = await _context.Inspections
            .Include(i => i.Project)
            .Include(i => i.Inspector)
            .Include(i => i.TpiAgency)
            .ToListAsync();

        return inspections.OrderByDescending(i => i.CreatedAt).ToList();
    }

    // GET: api/Inspections/5
    [HttpGet("{id}")]
    public async Task<ActionResult<Inspection>> GetInspection(Guid id)
    {
        var inspection = await _context.Inspections
            .Include(i => i.Project)
            .Include(i => i.Inspector)
            .Include(i => i.TpiAgency)
            .Include(i => i.Reviews)
            .FirstOrDefaultAsync(i => i.Id == id);

        if (inspection == null)
        {
            return NotFound();
        }

        return inspection;
    }

    // POST: api/Inspections
    [HttpPost]
    public async Task<ActionResult<Inspection>> CreateInspection(Inspection inspection)
    {
        _context.Inspections.Add(inspection);
        await _context.SaveChangesAsync();

        return CreatedAtAction(nameof(GetInspection), new { id = inspection.Id }, inspection);
    }

    // PUT: api/Inspections/5
    [HttpPut("{id}")]
    public async Task<IActionResult> UpdateInspection(Guid id, Inspection inspection)
    {
        if (id != inspection.Id)
        {
            return BadRequest();
        }

        var existing = await _context.Inspections.FindAsync(id);
        if (existing == null)
        {
            return NotFound();
        }

        // Only update fields if they are provided / not default
        if (!string.IsNullOrEmpty(inspection.PoNumber)) existing.PoNumber = inspection.PoNumber;
        if (!string.IsNullOrEmpty(inspection.NotificationNumber)) existing.NotificationNumber = inspection.NotificationNumber;
        if (inspection.NotificationRevision != null) existing.NotificationRevision = inspection.NotificationRevision;
        if (!string.IsNullOrEmpty(inspection.SupplierName)) existing.SupplierName = inspection.SupplierName;
        if (inspection.SubsupplierName != null) existing.SubsupplierName = inspection.SubsupplierName;
        if (inspection.SupplierAddress != null) existing.SupplierAddress = inspection.SupplierAddress;
        if (inspection.Country != null) existing.Country = inspection.Country;
        if (inspection.PoDescription != null) existing.PoDescription = inspection.PoDescription;
        if (inspection.InspectionType != null) existing.InspectionType = inspection.InspectionType;
        
        if (inspection.VendorContactName != null) existing.VendorContactName = inspection.VendorContactName;
        if (inspection.VendorContactPhone != null) existing.VendorContactPhone = inspection.VendorContactPhone;
        if (inspection.VendorContactEmail != null) existing.VendorContactEmail = inspection.VendorContactEmail;

        // Foreign keys (handle null values appropriately)
        if (inspection.ProjectId.HasValue) existing.ProjectId = inspection.ProjectId;
        if (inspection.AssignedInspectorId.HasValue) existing.AssignedInspectorId = inspection.AssignedInspectorId;
        if (inspection.TpiAgencyId.HasValue) existing.TpiAgencyId = inspection.TpiAgencyId;
        if (inspection.AssignedBy.HasValue) existing.AssignedBy = inspection.AssignedBy;

        // Dates
        if (inspection.NotificationDate.HasValue) existing.NotificationDate = inspection.NotificationDate;
        if (inspection.NotificationReceiptDate.HasValue) existing.NotificationReceiptDate = inspection.NotificationReceiptDate;
        if (inspection.StartDate.HasValue) existing.StartDate = inspection.StartDate;
        if (inspection.EndDate.HasValue) existing.EndDate = inspection.EndDate;
        if (inspection.ExpectedCompletionDate.HasValue) existing.ExpectedCompletionDate = inspection.ExpectedCompletionDate;
        if (inspection.ActualCompletionDate.HasValue) existing.ActualCompletionDate = inspection.ActualCompletionDate;
        
        if (inspection.AllInspectionDates != null) existing.AllInspectionDates = inspection.AllInspectionDates;
        if (inspection.InspectionTime != null) existing.InspectionTime = inspection.InspectionTime;
        if (inspection.LocationName != null) existing.LocationName = inspection.LocationName;
        if (inspection.LocationAddress != null) existing.LocationAddress = inspection.LocationAddress;
        if (inspection.LocationLatitude.HasValue) existing.LocationLatitude = inspection.LocationLatitude;
        if (inspection.LocationLongitude.HasValue) existing.LocationLongitude = inspection.LocationLongitude;

        // Status (always updated if sent)
        existing.Status = inspection.Status;

        // JSON string columns (only update if provided in the payload)
        if (inspection.ItemsBeingOffered != null) existing.ItemsBeingOffered = inspection.ItemsBeingOffered;
        if (inspection.InspectionReports != null) existing.InspectionReports = inspection.InspectionReports;
        if (inspection.InspectionActivities != null) existing.InspectionActivities = inspection.InspectionActivities;
        if (inspection.Notes != null) existing.Notes = inspection.Notes;
        if (inspection.ReleaseNoteUrl != null) existing.ReleaseNoteUrl = inspection.ReleaseNoteUrl;

        existing.UpdatedAt = DateTimeOffset.UtcNow;

        try
        {
            await _context.SaveChangesAsync();
        }
        catch (DbUpdateConcurrencyException)
        {
            if (!_context.Inspections.Any(e => e.Id == id))
            {
                return NotFound();
            }
            throw;
        }

        return NoContent();
    }

    // DELETE: api/Inspections/5
    [HttpDelete("{id}")]
    public async Task<IActionResult> DeleteInspection(Guid id)
    {
        var inspection = await _context.Inspections.FindAsync(id);
        if (inspection == null)
        {
            return NotFound();
        }

        _context.Inspections.Remove(inspection);
        await _context.SaveChangesAsync();

        return NoContent();
    }
}
