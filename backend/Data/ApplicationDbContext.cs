using InspectFlowBackend.Models;
using Microsoft.EntityFrameworkCore;

namespace InspectFlowBackend.Data;

public class ApplicationDbContext : DbContext
{
    public ApplicationDbContext(DbContextOptions<ApplicationDbContext> options) : base(options)
    {
    }

    public DbSet<Project> Projects => Set<Project>();
    public DbSet<TpiAgency> TpiAgencies => Set<TpiAgency>();
    public DbSet<Inspector> Inspectors => Set<Inspector>();
    public DbSet<Inspection> Inspections => Set<Inspection>();
    public DbSet<InspectionReview> InspectionReviews => Set<InspectionReview>();
    public DbSet<InspectionAttendance> InspectionAttendances => Set<InspectionAttendance>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        // Project Configuration
        modelBuilder.Entity<Project>(entity =>
        {
            entity.HasIndex(e => e.Code).IsUnique();
        });

        // TPI Agency Configuration
        modelBuilder.Entity<TpiAgency>(entity =>
        {
            entity.HasIndex(e => e.CompanyCode).IsUnique();
        });

        // Inspector Configuration
        modelBuilder.Entity<Inspector>(entity =>
        {
            entity.HasIndex(e => e.Email).IsUnique();
            
            entity.HasOne(i => i.TpiAgency)
                  .WithMany(t => t.Inspectors)
                  .HasForeignKey(i => i.TpiAgencyId)
                  .OnDelete(DeleteBehavior.SetNull);
        });

        // Inspection Configuration
        modelBuilder.Entity<Inspection>(entity =>
        {
            entity.HasIndex(e => e.NotificationNumber);
            entity.HasIndex(e => e.Status);
            entity.HasIndex(e => e.ProjectId);
            entity.HasIndex(e => e.AssignedInspectorId);

            entity.HasOne(i => i.Project)
                  .WithMany(p => p.Inspections)
                  .HasForeignKey(i => i.ProjectId)
                  .OnDelete(DeleteBehavior.SetNull);

            entity.HasOne(i => i.Inspector)
                  .WithMany(insp => insp.Inspections)
                  .HasForeignKey(i => i.AssignedInspectorId)
                  .OnDelete(DeleteBehavior.SetNull);

            entity.HasOne(i => i.TpiAgency)
                  .WithMany(t => t.Inspections)
                  .HasForeignKey(i => i.TpiAgencyId)
                  .OnDelete(DeleteBehavior.SetNull);
        });

        // Inspection Review Configuration
        modelBuilder.Entity<InspectionReview>(entity =>
        {
            entity.HasIndex(e => e.InspectionId);
            entity.HasIndex(e => e.InspectorId);

            entity.HasOne(r => r.Inspection)
                  .WithMany(i => i.Reviews)
                  .HasForeignKey(r => r.InspectionId)
                  .OnDelete(DeleteBehavior.Cascade);

            entity.HasOne(r => r.Inspector)
                  .WithMany(i => i.Reviews)
                  .HasForeignKey(r => r.InspectorId)
                  .OnDelete(DeleteBehavior.Cascade);
        });

        // Inspection Attendance Configuration
        modelBuilder.Entity<InspectionAttendance>(entity =>
        {
            entity.HasIndex(e => e.InspectionId);
            entity.HasIndex(e => e.InspectorId);

            entity.HasOne(a => a.Inspection)
                  .WithMany(i => i.Attendances)
                  .HasForeignKey(a => a.InspectionId)
                  .OnDelete(DeleteBehavior.Cascade);

            entity.HasOne(a => a.Inspector)
                  .WithMany(i => i.Attendances)
                  .HasForeignKey(a => a.InspectorId)
                  .OnDelete(DeleteBehavior.Cascade);
        });
    }
}
