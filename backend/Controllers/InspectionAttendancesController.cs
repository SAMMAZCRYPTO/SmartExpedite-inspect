using InspectFlowBackend.Data;
using InspectFlowBackend.Models;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace InspectFlowBackend.Controllers;

[ApiController]
[Route("api/[controller]")]
public class InspectionAttendancesController : ControllerBase
{
    private readonly ApplicationDbContext _context;

    public InspectionAttendancesController(ApplicationDbContext context)
    {
        _context = context;
    }

    // GET: api/InspectionAttendances
    [HttpGet]
    public async Task<ActionResult<IEnumerable<InspectionAttendance>>> GetInspectionAttendances([FromQuery] Guid? inspectionId)
    {
        IQueryable<InspectionAttendance> query = _context.InspectionAttendances.Include(a => a.Inspector);
        
        if (inspectionId.HasValue)
        {
            query = query.Where(a => a.InspectionId == inspectionId.Value);
        }

        var results = await query.ToListAsync();
        return results.OrderByDescending(a => a.CheckInTime).ToList();
    }

    // GET: api/InspectionAttendances/5
    [HttpGet("{id}")]
    public async Task<ActionResult<InspectionAttendance>> GetInspectionAttendance(Guid id)
    {
        var attendance = await _context.InspectionAttendances
            .Include(a => a.Inspector)
            .FirstOrDefaultAsync(a => a.Id == id);

        if (attendance == null)
        {
            return NotFound();
        }

        return attendance;
    }

    // POST: api/InspectionAttendances
    [HttpPost]
    public async Task<ActionResult<InspectionAttendance>> PostInspectionAttendance(InspectionAttendance attendance)
    {
        _context.InspectionAttendances.Add(attendance);
        await _context.SaveChangesAsync();

        return CreatedAtAction(nameof(GetInspectionAttendance), new { id = attendance.Id }, attendance);
    }

    // PUT: api/InspectionAttendances/5
    [HttpPut("{id}")]
    public async Task<IActionResult> PutInspectionAttendance(Guid id, InspectionAttendance attendance)
    {
        if (id != attendance.Id)
        {
            return BadRequest();
        }

        var existing = await _context.InspectionAttendances.FindAsync(id);
        if (existing == null)
        {
            return NotFound();
        }

        // Only update fields if they are provided / not default
        if (attendance.CheckInTime.HasValue) existing.CheckInTime = attendance.CheckInTime;
        if (attendance.CheckOutTime.HasValue) existing.CheckOutTime = attendance.CheckOutTime;
        if (attendance.CheckInLatitude.HasValue) existing.CheckInLatitude = attendance.CheckInLatitude;
        if (attendance.CheckInLongitude.HasValue) existing.CheckInLongitude = attendance.CheckInLongitude;
        if (attendance.CheckOutLatitude.HasValue) existing.CheckOutLatitude = attendance.CheckOutLatitude;
        if (attendance.CheckOutLongitude.HasValue) existing.CheckOutLongitude = attendance.CheckOutLongitude;
        existing.LocationVerified = attendance.LocationVerified;
        if (attendance.DistanceFromSiteMeters.HasValue) existing.DistanceFromSiteMeters = attendance.DistanceFromSiteMeters;
        if (attendance.CheckInNotes != null) existing.CheckInNotes = attendance.CheckInNotes;
        if (attendance.CheckOutNotes != null) existing.CheckOutNotes = attendance.CheckOutNotes;

        try
        {
            await _context.SaveChangesAsync();
        }
        catch (DbUpdateConcurrencyException)
        {
            if (!_context.InspectionAttendances.Any(e => e.Id == id))
            {
                return NotFound();
            }
            throw;
        }

        return NoContent();
    }

    // DELETE: api/InspectionAttendances/5
    [HttpDelete("{id}")]
    public async Task<IActionResult> DeleteInspectionAttendance(Guid id)
    {
        var attendance = await _context.InspectionAttendances.FindAsync(id);
        if (attendance == null)
        {
            return NotFound();
        }

        _context.InspectionAttendances.Remove(attendance);
        await _context.SaveChangesAsync();

        return NoContent();
    }
}
