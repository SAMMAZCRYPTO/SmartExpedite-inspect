import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { base44 } from '@/api/base44Client';

const ProjectContext = createContext();

export function ProjectProvider({ children }) {
  const [selectedProjectId, setSelectedProjectId] = useState(() => {
    return localStorage.getItem('selectedProjectId') || 'all';
  });
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState(null);

  const fetchProjectsAndUser = useCallback(async () => {
    try {
      const currentUser = await base44.auth.me();
      setUser(currentUser);
      if (!currentUser) {
        setProjects([]);
        setLoading(false);
        return;
      }

      const allProjects = await base44.entities.Project.list();
      const role = currentUser?.inspection_role || currentUser?.role;
      const isGlobalAdmin = currentUser?.role === 'admin' || role === 'admin';

      let availableProjects = [];
      if (isGlobalAdmin) {
        availableProjects = allProjects;
      } else {
        const uid = String(currentUser?.id || '').trim().toLowerCase();
        const uemail = String(currentUser?.email || '').trim().toLowerCase();
        const assignedIds = (currentUser?.project_ids || []).map((id) =>
          String(id).trim().toLowerCase()
        );
        availableProjects = allProjects.filter((p) => {
          const pid = String(p.id || '').trim().toLowerCase();
          if (assignedIds.includes(pid)) return true;
          if (uid && String(p.expediting_manager_id || '').trim().toLowerCase() === uid) return true;
          if (uid && String(p.inspection_manager_id || '').trim().toLowerCase() === uid) return true;
          if (uemail && String(p.expediting_manager_email || '').trim().toLowerCase() === uemail) return true;
          if (uemail && String(p.inspection_manager_email || '').trim().toLowerCase() === uemail) return true;
          const teamIds = (p.team_member_ids || []).map((t) => String(t).trim().toLowerCase());
          if (uid && teamIds.includes(uid)) return true;
          return false;
        });
      }

      setProjects(availableProjects);

      const savedId = localStorage.getItem('selectedProjectId');
      if (
        savedId &&
        (savedId === 'all' ||
          availableProjects.find(
            (p) => String(p.id).toLowerCase() === String(savedId).toLowerCase()
          ))
      ) {
        setSelectedProjectId(savedId);
      } else {
        setSelectedProjectId('all');
        localStorage.setItem('selectedProjectId', 'all');
      }
    } catch (error) {
      console.error('Failed to init project context:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProjectsAndUser();
    const handleRefresh = () => fetchProjectsAndUser();
    window.addEventListener('governance-updated', handleRefresh);
    return () => window.removeEventListener('governance-updated', handleRefresh);
  }, [fetchProjectsAndUser]);

  const handleProjectChange = (projectId) => {
    setSelectedProjectId(projectId);
    localStorage.setItem('selectedProjectId', projectId);
    window.dispatchEvent(
      new CustomEvent('project-context-changed', { detail: { projectId } })
    );
  };

  const currentProject =
    selectedProjectId && selectedProjectId !== 'all'
      ? projects.find(
          (p) =>
            String(p.id).toLowerCase() === String(selectedProjectId).toLowerCase()
        ) || null
      : null;

  return (
    <ProjectContext.Provider
      value={{
        selectedProjectId,
        setSelectedProjectId: handleProjectChange,
        projects,
        loading,
        currentProject,
        refreshProjects: fetchProjectsAndUser,
      }}
    >
      {children}
    </ProjectContext.Provider>
  );
}

export const useProject = () => useContext(ProjectContext);
