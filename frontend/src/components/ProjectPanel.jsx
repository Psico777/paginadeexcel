/**
 * EMFOX OMS v2 - ProjectPanel Component
 * Sidebar with saved projects list (Listas Guardadas)
 */
import React, { useState } from 'react';
import { FolderOpen, Plus, Trash2, X } from './Icons.jsx';

export default function ProjectPanel({
  projects,
  activeProjectId,
  onSelectProject,
  onCreateProject,
  onDeleteProject,
  onClose,
}) {
  const [newName, setNewName] = useState('');
  const [isCreating, setIsCreating] = useState(false);

  const handleCreate = async () => {
    const name = newName.trim();
    if (!name) return;
    setIsCreating(true);
    try {
      await onCreateProject(name);
      setNewName('');
    } finally {
      setIsCreating(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleCreate();
  };

  const handleDelete = (e, projectId) => {
    e.stopPropagation();
    if (window.confirm('¿Eliminar este proyecto? Los datos se perderán.')) {
      onDeleteProject(projectId);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleDateString('es-PE', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  };

  return (
    <div className="project-panel">
      <div className="project-panel-header">
        <h3><FolderOpen size={18} /> Listas Guardadas</h3>
        <button className="btn-icon" onClick={onClose} title="Cerrar">
          <X size={18} />
        </button>
      </div>

      {/* Create new */}
      <div className="project-create">
        <input
          type="text"
          placeholder="Nombre nueva lista..."
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isCreating}
        />
        <button
          className="btn-icon btn-create"
          onClick={handleCreate}
          disabled={!newName.trim() || isCreating}
          title="Crear"
        >
          <Plus size={18} />
        </button>
      </div>

      {/* Project list */}
      <div className="project-list">
        {projects.length === 0 && (
          <p className="project-empty">No hay listas guardadas</p>
        )}
        {projects.map((project) => (
          <div
            key={project.id}
            className={`project-item ${project.id === activeProjectId ? 'project-item-active' : ''}`}
            onClick={() => onSelectProject(project.id)}
          >
            <div className="project-item-info">
              <span className="project-item-name">{project.name}</span>
              <span className="project-item-meta">
                {formatDate(project.updated_at)}
                {project.product_count != null && ` • ${project.product_count} items`}
              </span>
            </div>
            <button
              className="btn-icon btn-delete-project"
              onClick={(e) => handleDelete(e, project.id)}
              title="Eliminar"
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
