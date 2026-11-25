import { User } from './csharpAuth';
import { getApiBaseUrl } from '../authFetch';

const API_BASE_URL = getApiBaseUrl();

const cleanDateField = (dateStr) => {
    if (!dateStr) return null;
    const dateStrClean = String(dateStr).trim();
    if (!dateStrClean || dateStrClean.toLowerCase() === 'n/a') return null;

    // If it's already a valid yyyy-MM-dd
    if (/^\d{4}-\d{2}-\d{2}$/.test(dateStrClean)) return dateStrClean;

    // Try parsing
    const parsed = Date.parse(dateStrClean);
    if (!isNaN(parsed)) {
        try {
            return new Date(parsed).toISOString().split('T')[0];
        } catch (e) {
            // Fallback
        }
    }

    // If it has ISO format but with time, e.g. yyyy-MM-ddT...
    const match = dateStrClean.match(/^(\d{4}-\d{2}-\d{2})/);
    if (match) return match[1];

    return null;
};

const sanitizePayload = (payload) => {
    if (!payload || typeof payload !== 'object') return payload;
    const newPayload = { ...payload };

    // Generate client-side UUID if missing
    if (!newPayload.id) {
        newPayload.id = crypto.randomUUID();
    }

    // C# Models expect generic JSON fields to be physically serialized as Strings
    const jsonFields = ['inspection_activities', 'items_being_offered', 'inspection_reports', 'test_reports', 'additional_reports', 'release_notes', 'findings'];
    jsonFields.forEach(field => {
        if (newPayload[field] && typeof newPayload[field] === 'object') {
            newPayload[field] = JSON.stringify(newPayload[field]);
        }
    });

    // Delete navigation properties that clash with C# navigation objects (resolved via foreign keys instead)
    const navigationProperties = ['tpi_agency', 'inspector', 'project', 'reviews', 'attendances', 'inspections'];
    navigationProperties.forEach(prop => {
        delete newPayload[prop];
    });

    // Clean and validate date fields to prevent C# DateTime deserialization from crashing
    const dateFields = ['start_date', 'end_date', 'notification_receipt_date', 'notification_date', 'expected_completion_date', 'actual_completion_date'];
    dateFields.forEach(field => {
        if (newPayload[field] !== undefined) {
            newPayload[field] = cleanDateField(newPayload[field]);
        }
    });

    // UUID fields - convert empty strings to null so they don't crash Guid parsers
    const uuidFields = ['project_id', 'inspector_id', 'tpi_agency_id', 'assigned_inspector_id', 'assigned_by', 'user_id'];
    uuidFields.forEach(field => {
        if (newPayload[field] === "") {
            newPayload[field] = null;
        }
    });

    // Number fields - convert empty strings to null
    const numberFields = ['distance_from_site_meters', 'report_quality_score', 'timeliness_score', 'communication_score', 'overall_score', 'location_latitude', 'location_longitude'];
    numberFields.forEach(field => {
        if (newPayload[field] === "") {
            newPayload[field] = null;
        }
    });

    return newPayload;
};

// Cache of TPI Agencies to avoid making extra network requests on every resolution
let tpiAgenciesCache = null;

const fetchTpiAgenciesOnce = async () => {
    if (tpiAgenciesCache) return tpiAgenciesCache;
    try {
        const response = await fetch(`${API_BASE_URL}/TpiAgencies`);
        if (response.ok) {
            tpiAgenciesCache = await response.json();
            return tpiAgenciesCache;
        }
    } catch (e) {
        console.error("Failed to fetch agencies for resolution:", e);
    }
    return [];
};

/**
 * Resolves agency names to database Guid IDs on save/create.
 */
const resolveTpiAgencyForInspector = async (payload) => {
    if (!payload.tpi_agency_id && payload.company) {
        const agencies = await fetchTpiAgenciesOnce();
        const agency = agencies.find(a => a.name === payload.company);
        if (agency) {
            payload.tpi_agency_id = agency.id;
        }
    }
    return payload;
};

const resolveTpiAgencyForInspection = async (payload) => {
    if (!payload.tpi_agency_id && payload.tpi_agency) {
        const agencies = await fetchTpiAgenciesOnce();
        const agency = agencies.find(a => a.name === payload.tpi_agency);
        if (agency) {
            payload.tpi_agency_id = agency.id;
        }
    }
    return payload;
};

/**
 * Coordinates Parser & Resolver for Inspection Attendance
 */
const parsePointStringToCoords = (coords) => {
    if (!coords) return null;
    if (typeof coords === 'string') {
        const match = coords.match(/POINT\(([-\d.]+) ([-\d.]+)\)/);
        if (match) {
            return {
                lng: parseFloat(match[1]),
                lat: parseFloat(match[2])
            };
        }
    }
    if (typeof coords === 'object') {
        if (coords.lng !== undefined && coords.lat !== undefined) {
            return coords;
        }
        if (coords.coordinates && Array.isArray(coords.coordinates)) {
            return { lng: coords.coordinates[0], lat: coords.coordinates[1] };
        }
    }
    return null;
};

const resolveCoordinatesForAttendance = (payload) => {
    if (payload.check_in_coordinates) {
        const coords = parsePointStringToCoords(payload.check_in_coordinates);
        if (coords) {
            payload.check_in_latitude = coords.lat;
            payload.check_in_longitude = coords.lng;
        }
    }
    if (payload.check_out_coordinates) {
        const coords = parsePointStringToCoords(payload.check_out_coordinates);
        if (coords) {
            payload.check_out_latitude = coords.lat;
            payload.check_out_longitude = coords.lng;
        }
    }
    return payload;
};

/**
 * Maps entity properties from backend database names to expected frontend properties.
 */
const formatDateToYmd = (dateStr) => {
    if (!dateStr) return null;
    const match = dateStr.match(/^(\d{4}-\d{2}-\d{2})/);
    return match ? match[1] : dateStr;
};

const parseJsonField = (fieldVal) => {
    if (!fieldVal) return [];
    if (typeof fieldVal === 'string') {
        try {
            return JSON.parse(fieldVal);
        } catch (e) {
            console.error("Failed to parse JSON field:", e, fieldVal);
            return [];
        }
    }
    return fieldVal;
};

const mapInspection = (inspection) => {
    if (!inspection) return inspection;
    return {
        ...inspection,
        start_date: formatDateToYmd(inspection.start_date),
        end_date: formatDateToYmd(inspection.end_date),
        notification_receipt_date: formatDateToYmd(inspection.notification_receipt_date),
        notification_date: formatDateToYmd(inspection.notification_date),
        // Parse JSON fields
        inspection_reports: parseJsonField(inspection.inspection_reports),
        inspection_activities: parseJsonField(inspection.inspection_activities),
        items_being_offered: parseJsonField(inspection.items_being_offered),
        // Map the relation properties to the flat/virtual fields the frontend expects
        tpi_agency: inspection.tpi_agency?.name || inspection.tpi_agency || null,
        assigned_inspector_name: inspection.inspector?.full_name || inspection.assigned_inspector_name || null,
        assigned_inspector_email: inspection.inspector?.email || inspection.assigned_inspector_email || null,
        assigned_inspector_phone: inspection.inspector?.phone || inspection.assigned_inspector_phone || null,
    };
};

const mapInspector = (inspector) => {
    if (!inspector) return inspector;
    return {
        ...inspector,
        // Map C# navigation property to company string for frontend Compatibility
        company: inspector.tpi_agency?.name || inspector.company || null,
    };
};

const mapAttendance = (attendance) => {
    if (!attendance) return attendance;
    return {
        ...attendance,
        inspector_name: attendance.inspector?.full_name || attendance.inspector_name || null,
        check_in_coordinates_text: attendance.check_in_latitude && attendance.check_in_longitude ? `POINT(${attendance.check_in_longitude} ${attendance.check_in_latitude})` : null,
        check_out_coordinates_text: attendance.check_out_latitude && attendance.check_out_longitude ? `POINT(${attendance.check_out_longitude} ${attendance.check_out_latitude})` : null,
    };
};

/**
 * Generic CRUD operations wrapper for C# ASP.NET Core API
 * Mimics the exact signature of the Supabase Base44 entity API pattern
 */
const createCSharpEntityWrapper = (endpoint) => ({
    list: async (filters = {}, options = {}) => {
        try {
            const origin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost';
            const url = new URL(`${API_BASE_URL}/${endpoint}`, origin);
            if (filters && typeof filters === 'object') {
                Object.entries(filters).forEach(([key, val]) => {
                    if (val !== undefined && val !== null) {
                        url.searchParams.append(key, val);
                    }
                });
            }
            const targetUrl = API_BASE_URL.startsWith('/') ? `${url.pathname}${url.search}` : url.toString();
            const response = await fetch(targetUrl);
            if (!response.ok) throw new Error('Network response was not ok');
            if (!response.ok) {
                let errMsg = `Request to ${endpoint} failed (${response.status})`;
                try {
                    const errBody = await response.json();
                    if (errBody?.detail) errMsg = typeof errBody.detail === 'string' ? errBody.detail : JSON.stringify(errBody.detail);
                } catch (_) { }
                throw new Error(errMsg);
            }
            const data = await response.json();

            // Map endpoints to frontend schema
            if (endpoint === 'Inspections') {
                return data.map(mapInspection);
            }
            if (endpoint === 'Inspectors') {
                return data.map(mapInspector);
            }
            if (endpoint === 'InspectionAttendances') {
                return data.map(mapAttendance);
            }
            return data;
        } catch (error) {
            console.error(`Error fetching ${endpoint}:`, error);
            throw error;
        }
    },

    get: async (id) => {
        try {
            const response = await fetch(`${API_BASE_URL}/${endpoint}/${id}`);
            if (!response.ok) throw new Error('Network response was not ok');
            if (!response.ok) {
                let errMsg = `Request to ${endpoint} failed (${response.status})`;
                try {
                    const errBody = await response.json();
                    if (errBody?.detail) errMsg = typeof errBody.detail === 'string' ? errBody.detail : JSON.stringify(errBody.detail);
                } catch (_) { }
                throw new Error(errMsg);
            }
            const data = await response.json();

            // Map endpoints to frontend schema
            if (endpoint === 'Inspections') {
                return mapInspection(data);
            }
            if (endpoint === 'Inspectors') {
                return mapInspector(data);
            }
            if (endpoint === 'InspectionAttendances') {
                return mapAttendance(data);
            }
            return data;
        } catch (error) {
            console.error(`Error fetching ${endpoint}/${id}:`, error);
            throw error;
        }
    },

    create: async (payload) => {
        try {
            let sanitized = sanitizePayload(payload);

            // Resolve relation references and coordinates
            if (endpoint === 'Inspectors') {
                sanitized = await resolveTpiAgencyForInspector(sanitized);
            } else if (endpoint === 'Inspections') {
                sanitized = await resolveTpiAgencyForInspection(sanitized);
                if (!sanitized.created_by) {
                    try {
                        const currentUser = await User.getUser();
                        if (currentUser?.email) {
                            sanitized.created_by = currentUser.email;
                        }
                    } catch (e) {
                        console.warn("Failed to automatically set created_by:", e);
                    }
                }
            } else if (endpoint === 'InspectionAttendances') {
                sanitized = resolveCoordinatesForAttendance(sanitized);
            }

            const response = await fetch(`${API_BASE_URL}/${endpoint}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(sanitized)
            });
            if (!response.ok) throw new Error('Network response was not ok');
            if (!response.ok) {
                let errMsg = `Request to ${endpoint} failed (${response.status})`;
                try {
                    const errBody = await response.json();
                    if (errBody?.detail) errMsg = typeof errBody.detail === 'string' ? errBody.detail : JSON.stringify(errBody.detail);
                } catch (_) { }
                throw new Error(errMsg);
            }
            const data = await response.json();

            // Clear cache on creation to keep it fresh
            tpiAgenciesCache = null;

            if (endpoint === 'Inspections') {
                return mapInspection(data);
            }
            if (endpoint === 'Inspectors') {
                return mapInspector(data);
            }
            if (endpoint === 'InspectionAttendances') {
                return mapAttendance(data);
            }
            return data;
        } catch (error) {
            console.error(`Error creating ${endpoint}:`, error);
            throw error;
        }
    },

    update: async (id, payload) => {
        try {
            const payloadWithId = { ...payload, id };
            let sanitized = sanitizePayload(payloadWithId);

            // Resolve relation references and coordinates
            if (endpoint === 'Inspectors') {
                sanitized = await resolveTpiAgencyForInspector(sanitized);
            } else if (endpoint === 'Inspections') {
                sanitized = await resolveTpiAgencyForInspection(sanitized);
            } else if (endpoint === 'InspectionAttendances') {
                sanitized = resolveCoordinatesForAttendance(sanitized);
            }

            const response = await fetch(`${API_BASE_URL}/${endpoint}/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(sanitized)
            });
            if (!response.ok) throw new Error('Network response was not ok');
            if (!response.ok) {
                let errMsg = `Request to ${endpoint} failed (${response.status})`;
                try {
                    const errBody = await response.json();
                    if (errBody?.detail) errMsg = typeof errBody.detail === 'string' ? errBody.detail : JSON.stringify(errBody.detail);
                } catch (_) { }
                throw new Error(errMsg);
            }

            // Clear cache on updates to keep it fresh
            tpiAgenciesCache = null;

            // PUT may return 204; refetch authoritative server copy instead of shallow client merge
            if (response.status === 204) {
                return await createCSharpEntityWrapper(endpoint).get(id);
            }

            const data = await response.json();
            if (endpoint === 'Inspections') {
                return mapInspection(data);
            }
            if (endpoint === 'Inspectors') {
                return mapInspector(data);
            }
            if (endpoint === 'InspectionAttendances') {
                return mapAttendance(data);
            }
            return data;
        } catch (error) {
            console.error(`Error updating ${endpoint}/${id}:`, error);
            throw error;
        }
    },

    delete: async (id) => {
        try {
            const response = await fetch(`${API_BASE_URL}/${endpoint}/${id}`, {
                method: 'DELETE'
            });
            if (!response.ok) throw new Error('Network response was not ok');
            if (!response.ok) {
                let errMsg = `Request to ${endpoint} failed (${response.status})`;
                try {
                    const errBody = await response.json();
                    if (errBody?.detail) errMsg = typeof errBody.detail === 'string' ? errBody.detail : JSON.stringify(errBody.detail);
                } catch (_) { }
                throw new Error(errMsg);
            }
            // Clear cache on delete to keep it fresh
            tpiAgenciesCache = null;
        } catch (error) {
            console.error(`Error deleting ${endpoint}/${id}:`, error);
            throw error;
        }
    },

    count: async (filters = {}) => {
        const data = await createCSharpEntityWrapper(endpoint).list(filters);
        return data.length;
    },

    subscribe: (callback, filters = {}) => {
        console.warn(`Realtime subscriptions for C# ${endpoint} are not yet implemented with SignalR.`);
        return { unsubscribe: () => { } };
    }
});

export const Inspection = createCSharpEntityWrapper('Inspections');
export const Inspector = createCSharpEntityWrapper('Inspectors');
export const TPIAgency = createCSharpEntityWrapper('TpiAgencies');
export const Project = createCSharpEntityWrapper('Projects');
export const InspectionAttendance = createCSharpEntityWrapper('InspectionAttendances');
export const InspectionReview = createCSharpEntityWrapper('InspectionReviews');
