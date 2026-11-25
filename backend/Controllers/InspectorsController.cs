using InspectFlowBackend.Data;
using InspectFlowBackend.Models;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace InspectFlowBackend.Controllers;

[ApiController]
[Route("api/[controller]")]
public class InspectorsController : ControllerBase
{
    private readonly ApplicationDbContext _context;

    public InspectorsController(ApplicationDbContext context)
    {
        _context = context;
    }

    // GET: api/Inspectors
    [HttpGet]
    public async Task<ActionResult<IEnumerable<Inspector>>> GetInspectors()
    {
        return await _context.Inspectors
            .Include(i => i.TpiAgency)
            .ToListAsync();
    }

    // GET: api/Inspectors/5
    [HttpGet("{id}")]
    public async Task<ActionResult<Inspector>> GetInspector(Guid id)
    {
        var inspector = await _context.Inspectors
            .Include(i => i.TpiAgency)
            .FirstOrDefaultAsync(i => i.Id == id);

        if (inspector == null)
        {
            return NotFound();
        }

        return inspector;
    }

    // POST: api/Inspectors
    [HttpPost]
    public async Task<ActionResult<Inspector>> PostInspector(Inspector inspector)
    {
        _context.Inspectors.Add(inspector);
        await _context.SaveChangesAsync();

        return CreatedAtAction(nameof(GetInspector), new { id = inspector.Id }, inspector);
    }

    // PUT: api/Inspectors/5
    [HttpPut("{id}")]
    public async Task<IActionResult> PutInspector(Guid id, Inspector inspector)
    {
        if (id != inspector.Id)
        {
            return BadRequest();
        }

        var existingInspector = await _context.Inspectors.FindAsync(id);
        if (existingInspector == null)
        {
            return NotFound();
        }

        // Only update fields if they are provided / not default
        if (!string.IsNullOrEmpty(inspector.FullName)) existingInspector.FullName = inspector.FullName;
        if (!string.IsNullOrEmpty(inspector.Email)) existingInspector.Email = inspector.Email;
        if (inspector.Phone != null) existingInspector.Phone = inspector.Phone;
        if (inspector.Specialization != null) existingInspector.Specialization = inspector.Specialization;
        if (inspector.Certifications != null) existingInspector.Certifications = inspector.Certifications;
        if (inspector.ExperienceYears.HasValue) existingInspector.ExperienceYears = inspector.ExperienceYears;
        if (inspector.CvUrl != null) existingInspector.CvUrl = inspector.CvUrl;
        if (inspector.PhotoUrl != null) existingInspector.PhotoUrl = inspector.PhotoUrl;
        
        // Handle agency ID updates (allowing null if explicitly set to none)
        existingInspector.TpiAgencyId = inspector.TpiAgencyId;
        existingInspector.Status = inspector.Status;
        existingInspector.UpdatedAt = DateTimeOffset.UtcNow;

        try
        {
            await _context.SaveChangesAsync();
        }
        catch (DbUpdateConcurrencyException)
        {
            if (!_context.Inspectors.Any(e => e.Id == id))
            {
                return NotFound();
            }
            throw;
        }

        return NoContent();
    }

    // DELETE: api/Inspectors/5
    [HttpDelete("{id}")]
    public async Task<IActionResult> DeleteInspector(Guid id)
    {
        var inspector = await _context.Inspectors.FindAsync(id);
        if (inspector == null)
        {
            return NotFound();
        }

        _context.Inspectors.Remove(inspector);
        await _context.SaveChangesAsync();

        return NoContent();
    }
}
