using InspectFlowBackend.Data;
using InspectFlowBackend.Models;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace InspectFlowBackend.Controllers;

[ApiController]
[Route("api/[controller]")]
public class InspectionReviewsController : ControllerBase
{
    private readonly ApplicationDbContext _context;

    public InspectionReviewsController(ApplicationDbContext context)
    {
        _context = context;
    }

    // GET: api/InspectionReviews
    [HttpGet]
    public async Task<ActionResult<IEnumerable<InspectionReview>>> GetInspectionReviews()
    {
        var reviews = await _context.InspectionReviews
            .Include(r => r.Inspector)
            .ToListAsync();

        return reviews.OrderByDescending(r => r.ReviewDate).ToList();
    }

    // GET: api/InspectionReviews/5
    [HttpGet("{id}")]
    public async Task<ActionResult<InspectionReview>> GetInspectionReview(Guid id)
    {
        var review = await _context.InspectionReviews
            .Include(r => r.Inspector)
            .FirstOrDefaultAsync(r => r.Id == id);

        if (review == null)
        {
            return NotFound();
        }

        return review;
    }

    // POST: api/InspectionReviews
    [HttpPost]
    public async Task<ActionResult<InspectionReview>> PostInspectionReview(InspectionReview review)
    {
        _context.InspectionReviews.Add(review);
        await _context.SaveChangesAsync();

        return CreatedAtAction(nameof(GetInspectionReview), new { id = review.Id }, review);
    }

    // PUT: api/InspectionReviews/5
    [HttpPut("{id}")]
    public async Task<IActionResult> PutInspectionReview(Guid id, InspectionReview review)
    {
        if (id != review.Id)
        {
            return BadRequest();
        }

        _context.Entry(review).State = EntityState.Modified;

        try
        {
            await _context.SaveChangesAsync();
        }
        catch (DbUpdateConcurrencyException)
        {
            if (!_context.InspectionReviews.Any(e => e.Id == id))
            {
                return NotFound();
            }
            throw;
        }

        return NoContent();
    }

    // DELETE: api/InspectionReviews/5
    [HttpDelete("{id}")]
    public async Task<IActionResult> DeleteInspectionReview(Guid id)
    {
        var review = await _context.InspectionReviews.FindAsync(id);
        if (review == null)
        {
            return NotFound();
        }

        _context.InspectionReviews.Remove(review);
        await _context.SaveChangesAsync();

        return NoContent();
    }
}
