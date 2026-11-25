import React from 'react';
import { useProject } from '../context/ProjectContext';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { FolderKanban, Users } from "lucide-react";

export default function ProjectSelector({ mobile = false }) {
  const { projects, selectedProjectId, setSelectedProjectId, currentProject, loading } = useProject();

  if (loading) return <div className="w-40 h-9 bg-gray-100 animate-pulse rounded-md" />;

  if (projects.length === 0) {
    return (
      <div className="flex items-center gap-2 text-xs text-gray-500 px-3 py-1.5 bg-gray-50 rounded-md border">
        <FolderKanban className="w-3.5 h-3.5" />
        <span>No Projects Assigned</span>
      </div>
    );
  }

  return (
    <div className={`flex items-center gap-2 ${mobile ? 'w-full flex-col items-start' : ''}`}>
      <div className={`flex items-center gap-1.5 ${mobile ? 'w-full' : ''}`}>
        <FolderKanban className={`w-4 h-4 text-indigo-600 shrink-0 ${mobile ? 'hidden' : ''}`} />
        <Select value={selectedProjectId || "all"} onValueChange={setSelectedProjectId}>
          <SelectTrigger className={`${mobile ? 'w-full' : 'w-[250px]'} h-8 text-xs font-semibold bg-white border-gray-300 focus:ring-indigo-500`}>
            <SelectValue placeholder="Select Project" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all" className="text-xs font-bold text-indigo-700">
              All Assigned Projects ({projects.length})
            </SelectItem>
            {projects.map((project) => (
              <SelectItem key={project.id} value={project.id} className="text-xs">
                <span className="font-mono font-bold text-gray-700 mr-1.5">[{project.code}]</span>
                <span>{project.name}</span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {currentProject && !mobile && (
        <div
          className="hidden xl:flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-indigo-50/80 border border-indigo-200/80 text-[10px] text-indigo-900 shrink-0"
          title={`Expediting Mgr: ${currentProject.expediting_manager_name || 'Assigned'} | QC/Inspection Mgr: ${currentProject.inspection_manager_name || 'Assigned'}`}
        >
          <Users className="w-3 h-3 text-indigo-600 shrink-0" />
          <span>
            <b>Exp Mgr:</b> {(currentProject.expediting_manager_name || "Tariq").split("(")[0].trim()}
          </span>
          <span className="text-indigo-300">|</span>
          <span>
            <b>QC Mgr:</b> {(currentProject.inspection_manager_name || "Dr. Henrik").split("(")[0].trim()}
          </span>
        </div>
      )}
    </div>
  );
}
