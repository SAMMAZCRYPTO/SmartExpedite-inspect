import { getApiBaseUrl } from './authFetch';

const API_BASE_URL = getApiBaseUrl();

/**
 * Storage helper functions for file uploads to C# ASP.NET Core API
 */

const uploadFileToCSharp = async (file, bucket, path) => {
    try {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('bucket', bucket);
        formData.append('path', path);

        const response = await fetch(`${API_BASE_URL}/Storage/upload`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error(`Upload failed with status: ${response.status}`);
        }

        const data = await response.json();
        return data.url; // Returns public URL of the uploaded file
    } catch (error) {
        console.error('File upload error:', error);
        throw error;
    }
};

// ============================================================================
// INSPECTION DOCUMENTS BUCKET
// ============================================================================

/**
 * Upload an inspection notification PDF
 */
export const uploadInspectionNotification = async (file, inspectionId) => {
    const path = `${inspectionId}/notifications/${Date.now()}_${file.name}`;
    return await uploadFileToCSharp(file, 'inspection-documents', path);
};

/**
 * Upload an inspection report (Flash, Interim, Final)
 */
export const uploadInspectionReport = async (file, inspectionId, reportType) => {
    const path = `${inspectionId}/reports/${reportType}/${Date.now()}_${file.name}`;
    return await uploadFileToCSharp(file, 'inspection-documents', path);
};

/**
 * Upload an Inspection Release Certificate (IRC)
 */
export const uploadReleaseNote = async (file, inspectionId) => {
    const path = `${inspectionId}/release-notes/${Date.now()}_${file.name}`;
    return await uploadFileToCSharp(file, 'inspection-documents', path);
};

/**
 * Upload finding photo/evidence
 */
export const uploadFindingPhoto = async (file, inspectionId, findingId) => {
    const path = `${inspectionId}/findings/${findingId}/${Date.now()}_${file.name}`;
    return await uploadFileToCSharp(file, 'inspection-documents', path);
};

// ============================================================================
// INSPECTOR CVS BUCKET
// ============================================================================

/**
 * Upload inspector CV
 */
export const uploadInspectorCV = async (file, inspectorId) => {
    const path = `${inspectorId}/cv_${Date.now()}_${file.name}`;
    return await uploadFileToCSharp(file, 'inspector-cvs', path);
};

// ============================================================================
// AVATARS BUCKET
// ============================================================================

/**
 * Upload user avatar/profile picture
 */
export const uploadAvatar = async (file, userId) => {
    const path = `${userId}/avatar_${Date.now()}.${file.name.split('.').pop()}`;
    return await uploadFileToCSharp(file, 'avatars', path);
};

// ============================================================================
// GENERIC HELPER FUNCTIONS
// ============================================================================

/**
 * Delete a file from storage
 */
export const deleteFile = async (bucket, path) => {
    try {
        const response = await fetch(`${API_BASE_URL}/Storage/delete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ bucket, path })
        });

        if (!response.ok) {
            throw new Error(`Delete failed with status: ${response.status}`);
        }
    } catch (error) {
        console.error('File deletion error:', error);
        throw error;
    }
};

/**
 * Get download URL for a file
 */
export const getDownloadURL = async (bucket, path, expiresIn = 3600) => {
    // In local file storage, the URL is direct and doesn't require signing
    const staticBase = API_BASE_URL.replace('/api', '');
    return `${staticBase}/uploads/${bucket}/${path}`;
};

/**
 * List files in a specific path
 */
export const listFiles = async (bucket, path = '') => {
    // Mocked list files since it is not used in the UI
    return [];
};
