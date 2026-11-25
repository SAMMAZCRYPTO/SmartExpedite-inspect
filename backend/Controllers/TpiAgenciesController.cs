using InspectFlowBackend.Data;
using InspectFlowBackend.Models;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace InspectFlowBackend.Controllers;

[ApiController]
[Route("api/[controller]")]
public class TpiAgenciesController : ControllerBase
{
    private readonly ApplicationDbContext _context;

    public TpiAgenciesController(ApplicationDbContext context)
    {
        _context = context;
    }

    [HttpGet]
    public async Task<ActionResult<IEnumerable<TpiAgency>>> GetTpiAgencies()
    {
        return await _context.TpiAgencies.ToListAsync();
    }

    [HttpGet("{id}")]
    public async Task<ActionResult<TpiAgency>> GetTpiAgency(Guid id)
    {
        var agency = await _context.TpiAgencies.FindAsync(id);
        if (agency == null) return NotFound();
        return agency;
    }

    [HttpPost]
    public async Task<ActionResult<TpiAgency>> PostTpiAgency(TpiAgency tpiAgency)
    {
        _context.TpiAgencies.Add(tpiAgency);
        await _context.SaveChangesAsync();
        return CreatedAtAction(nameof(GetTpiAgency), new { id = tpiAgency.Id }, tpiAgency);
    }

    [HttpPut("{id}")]
    public async Task<IActionResult> PutTpiAgency(Guid id, TpiAgency tpiAgency)
    {
        if (id != tpiAgency.Id)
        {
            return BadRequest();
        }

        _context.Entry(tpiAgency).State = EntityState.Modified;
        tpiAgency.UpdatedAt = DateTimeOffset.UtcNow;

        try
        {
            await _context.SaveChangesAsync();
        }
        catch (DbUpdateConcurrencyException)
        {
            if (!_context.TpiAgencies.Any(e => e.Id == id))
            {
                return NotFound();
            }
            throw;
        }

        return NoContent();
    }

    [HttpDelete("{id}")]
    public async Task<IActionResult> DeleteTpiAgency(Guid id)
    {
        var agency = await _context.TpiAgencies.FindAsync(id);
        if (agency == null)
        {
            return NotFound();
        }

        _context.TpiAgencies.Remove(agency);
        await _context.SaveChangesAsync();

        return NoContent();
    }

    [HttpGet("performance")]
    public async Task<ActionResult<IEnumerable<object>>> GetPerformance()
    {
        var agencies = await _context.TpiAgencies
            .Include(a => a.Inspectors)
                .ThenInclude(insp => insp.Inspections)
                    .ThenInclude(i => i.Reviews)
            .ToListAsync();

        var result = agencies.Select(a => {
            var inspectors = a.Inspectors.ToList();
            var inspections = inspectors.SelectMany(insp => insp.Inspections).ToList();
            var reviews = inspections.SelectMany(i => i.Reviews).ToList();

            var totalInspections = inspections.Count;
            var completedInspections = inspections.Count(i => i.Status == InspectionStatus.Completed);
            var receivedInspections = inspections.Count(i => i.Status == InspectionStatus.Received);
            var inProgressInspections = inspections.Count(i => i.Status == InspectionStatus.InProgress);
            var scheduledInspections = inspections.Count(i => i.Status == InspectionStatus.Scheduled);

            double? avgOverallScore = reviews.Any(r => r.OverallScore.HasValue) 
                ? Math.Round(reviews.Where(r => r.OverallScore.HasValue).Average(r => r.OverallScore!.Value), 1) 
                : null;
            
            double? avgQualityScore = reviews.Any(r => r.ReportQualityScore.HasValue) 
                ? Math.Round(reviews.Where(r => r.ReportQualityScore.HasValue).Average(r => r.ReportQualityScore!.Value), 1) 
                : null;

            double? avgTimelinessScore = reviews.Any(r => r.TimelinessScore.HasValue) 
                ? Math.Round(reviews.Where(r => r.TimelinessScore.HasValue).Average(r => r.TimelinessScore!.Value), 1) 
                : null;

            double? avgCommunicationScore = reviews.Any(r => r.CommunicationScore.HasValue) 
                ? Math.Round(reviews.Where(r => r.CommunicationScore.HasValue).Average(r => r.CommunicationScore!.Value), 1) 
                : null;

            var activeInspectors = inspectors.Count(insp => insp.Status == InspectorStatus.Active);
            var totalInspectors = inspectors.Count;

            double? onTimeCompletionRate = null;
            var completedWithDates = inspections.Where(i => i.ActualCompletionDate.HasValue).ToList();
            if (completedWithDates.Any())
            {
                var onTimeCount = completedWithDates.Count(i => i.ExpectedCompletionDate.HasValue && i.ActualCompletionDate <= i.ExpectedCompletionDate);
                onTimeCompletionRate = Math.Round((double)onTimeCount / completedWithDates.Count * 100, 1);
            }

            var totalMissedNcrs = reviews.Sum(r => r.MissedNcrCount);
            var totalFalseNcrs = reviews.Sum(r => r.FalseNcrCount);

            return new {
                agency_id = a.Id,
                agency_name = a.Name,
                company_code = a.CompanyCode,
                manager_name = a.ManagerName,
                manager_email = a.ManagerEmail,
                agency_status = a.Status,

                total_inspections = totalInspections,
                completed_inspections = completedInspections,
                received_inspections = receivedInspections,
                in_progress_inspections = inProgressInspections,
                scheduled_inspections = scheduledInspections,

                avg_overall_score = avgOverallScore ?? 0,
                avg_quality_score = avgQualityScore ?? 0,
                avg_timeliness_score = avgTimelinessScore ?? 0,
                avg_communication_score = avgCommunicationScore ?? 0,

                active_inspectors = activeInspectors,
                total_inspectors = totalInspectors,
                on_time_completion_rate = onTimeCompletionRate ?? 0,

                total_ncrs = 0,
                total_findings = 0,

                total_missed_ncrs = totalMissedNcrs,
                total_false_ncrs = totalFalseNcrs
            };
        });

        return Ok(result);
    }
}
