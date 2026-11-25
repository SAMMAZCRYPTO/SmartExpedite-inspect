import { User, Inspection } from './entities';
import { getApiBaseUrl } from './authFetch';

const aiBase = () => `${getApiBaseUrl()}/v2/ai`;

/**
 * Parse an inspection notification PDF via secured backend AI proxy (API key stays on server)
 */
export const parseInspectionNotification = async (fileUrl, fileName) => {
    const response = await fetch(`${aiBase()}/extract-notification`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_url: fileUrl, file_name: fileName }),
    });
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.detail || `AI extraction error (${response.status})`);
    }
    return data.output ?? data;
};

/**
 * Parse an inspection report PDF via secured backend AI proxy
 */
export const parseInspectionReport = async (fileUrl, fileName, reportType) => {
    const response = await fetch(`${aiBase()}/extract-report`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            file_url: fileUrl,
            file_name: fileName,
            report_type: reportType || 'Flash',
        }),
    });
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.detail || `AI report extraction error (${response.status})`);
    }
    return data.output ?? data;
};

/**
 * Generic document extraction proxy replacing direct browser Gemini calls
 */
export const invokeAIDocumentPrompt = async ({ prompt, file_urls, response_json_schema }) => {
    const response = await fetch(`${aiBase()}/invoke`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, file_urls, response_json_schema }),
    });
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.detail || `AI analysis error (${response.status})`);
    }
    return data;
};

export const uploadAndParseNotification = async (file, projectId = null) => {
    const { uploadInspectionNotification } = await import('./storage');
    const tempId = crypto.randomUUID();
    const fileUrl = await uploadInspectionNotification(file, tempId);
    const parsedData = await parseInspectionNotification(fileUrl, file.name);
    return {
        ...parsedData,
        project_id: projectId,
        notification_file_url: fileUrl,
        status: 'received',
        created_at: new Date().toISOString(),
    };
};

export const uploadAndParseReport = async (file, inspectionId, reportType) => {
    const { uploadInspectionReport } = await import('./storage');
    const fileUrl = await uploadInspectionReport(file, inspectionId, reportType);
    const parsedData = await parseInspectionReport(fileUrl, file.name, reportType);
    const user = await User.getUser();

    return {
        id: crypto.randomUUID(),
        type: reportType,
        upload_date: new Date().toISOString(),
        report_url: fileUrl,
        uploaded_by: user?.id || null,
        findings: parsedData.findings || [],
        report_summary: parsedData.report_summary || '',
        overall_result: parsedData.overall_result || 'PENDING',
        test_results: parsedData.test_results || [],
        recommendations: parsedData.recommendations || '',
        approval_status: 'pending',
        approved_by: null,
        approval_date: null,
        rejection_reason: null,
    };
};

export const addReportToInspection = async (inspectionId, reportData) => {
    const inspection = await Inspection.get(inspectionId);
    let rawReports = inspection.inspection_reports;
    let parsedReports = [];
    if (rawReports) {
        if (typeof rawReports === 'string') {
            parsedReports = JSON.parse(rawReports);
        } else if (Array.isArray(rawReports)) {
            parsedReports = rawReports;
        }
    }
    const updatedReports = [...parsedReports, reportData];
    return await Inspection.update(inspectionId, { inspection_reports: updatedReports });
};
