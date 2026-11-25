using Microsoft.AspNetCore.Mvc;

namespace InspectFlowBackend.Controllers;

[ApiController]
[Route("api/[controller]")]
public class StorageController : ControllerBase
{
    private readonly IWebHostEnvironment _env;

    public StorageController(IWebHostEnvironment env)
    {
        _env = env;
    }

    [HttpPost("upload")]
    public async Task<IActionResult> Upload([FromForm] IFormFile file, [FromForm] string bucket, [FromForm] string path)
    {
        if (file == null || file.Length == 0)
        {
            return BadRequest("No file was uploaded.");
        }

        if (string.IsNullOrEmpty(bucket) || string.IsNullOrEmpty(path))
        {
            return BadRequest("Bucket and path parameters are required.");
        }

        try
        {
            // Sanitize subpath to prevent path traversal attacks
            if (path.Contains(".."))
            {
                return BadRequest("Invalid path.");
            }

            // Create target folder structure inside wwwroot/uploads/{bucket}
            string uploadsFolder = Path.Combine(_env.WebRootPath ?? "wwwroot", "uploads", bucket);
            string fileSubpath = path.Replace('/', Path.DirectorySeparatorChar);
            string fullPath = Path.Combine(uploadsFolder, fileSubpath);
            
            string? directoryName = Path.GetDirectoryName(fullPath);
            if (directoryName != null && !Directory.Exists(directoryName))
            {
                Directory.CreateDirectory(directoryName);
            }

            // Save file
            using (var stream = new FileStream(fullPath, FileMode.Create))
            {
                await file.CopyToAsync(stream);
            }

            // Generate public URL
            var request = HttpContext.Request;
            var baseUrl = $"{request.Scheme}://{request.Host}";
            var publicUrl = $"{baseUrl}/uploads/{bucket}/{path.TrimStart('/')}";

            return Ok(new { url = publicUrl });
        }
        catch (Exception ex)
        {
            return StatusCode(500, $"Internal server error: {ex.Message}");
        }
    }

    [HttpPost("delete")]
    public IActionResult Delete([FromBody] DeleteFileRequest request)
    {
        if (string.IsNullOrEmpty(request.Bucket) || string.IsNullOrEmpty(request.Path))
        {
            return BadRequest("Bucket and path parameters are required.");
        }

        try
        {
            if (request.Path.Contains(".."))
            {
                return BadRequest("Invalid path.");
            }

            string uploadsFolder = Path.Combine(_env.WebRootPath ?? "wwwroot", "uploads", request.Bucket);
            string fileSubpath = request.Path.Replace('/', Path.DirectorySeparatorChar);
            string fullPath = Path.Combine(uploadsFolder, fileSubpath);

            if (System.IO.File.Exists(fullPath))
            {
                System.IO.File.Delete(fullPath);
                return Ok(new { message = "File deleted successfully" });
            }

            return NotFound("File not found");
        }
        catch (Exception ex)
        {
            return StatusCode(500, $"Internal server error: {ex.Message}");
        }
    }
}

public class DeleteFileRequest
{
    public string Bucket { get; set; } = string.Empty;
    public string Path { get; set; } = string.Empty;
}
