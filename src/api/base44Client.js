/**
 * Backward compatibility layer for Base44 client
 * Now re-exports C# API-based entities with Base44-compatible API
 */
import * as entities from './entities';
import { invokeAIDocumentPrompt, parseInspectionNotification } from './ai';
import { getApiBaseUrl } from './authFetch';

// Re-export all entities as base44 for backward compatibility
export const base44 = {
  auth: entities.auth,
  // Add other entities as needed by the app
  Inspection: entities.Inspection,
  Inspector: entities.Inspector,
  TPIAgency: entities.TPIAgency,
  Project: entities.Project,
  InspectionAttendance: entities.InspectionAttendance,
  InspectionReview: entities.InspectionReview,
  User: entities.User,
  entities: {
    Inspection: entities.Inspection,
    Inspector: entities.Inspector,
    TPIAgency: entities.TPIAgency,
    Project: entities.Project,
    InspectionAttendance: entities.InspectionAttendance,
    InspectionReview: entities.InspectionReview,
    User: entities.User,
  },
  // Base44-compatible file integration
  integrations: {
    Core: {
      /**
       * Upload a file to Supabase Storage
       * @param {Object} params - { file: File }
       * @returns {Promise<{file_url: string}>}
       */
      UploadFile: async ({ file }) => {
        try {
          const fileName = file.name.replace(/[^a-zA-Z0-9._-]/g, '_');
          const path = `uploads/${Date.now()}_${fileName}`;

          const formData = new FormData();
          formData.append('file', file);
          formData.append('bucket', 'inspection-documents');
          formData.append('path', path);

          const backendUrl = getApiBaseUrl();
          const response = await fetch(`${backendUrl}/Storage/upload`, {
            method: 'POST',
            body: formData,
          });

          if (!response.ok) {
            const errText = await response.text();
            throw new Error(`File upload failed (${response.status}): ${errText}`);
          }
          const data = await response.json();
          return { file_url: data.url };
        } catch (error) {
          console.error('Upload error:', error);
          throw error;
        }
      },

      /**
       * Extract data from an uploaded file using Gemini AI
       * @param {Object} params - { file_url: string, json_schema: Object }
       * @returns {Promise<{status: string, output: Object, details?: string}>}
       */
      ExtractDataFromUploadedFile: async ({ file_url, json_schema }) => {
        try {
          if (json_schema) {
            const output = await invokeAIDocumentPrompt({
              prompt: 'Extract structured fields accurately from the uploaded document using the provided JSON schema.',
              file_urls: [file_url],
              response_json_schema: json_schema,
            });
            return { status: 'success', output };
          }
          const result = await parseInspectionNotification(file_url, file_url.split('/').pop());
          return {
            status: 'success',
            output: result
          };
        } catch (error) {
          console.error('Extraction error:', error);
          return {
            status: 'error',
            output: null,
            details: error.message || 'Failed to extract data'
          };
        }
      },

      /**
       * Invoke server-side AI proxy for structured report/document extraction
       * @param {Object} params - { prompt: string, file_urls: string[], response_json_schema: Object }
       * @returns {Promise<Object>} Extracted data
       */
      InvokeLLM: async ({ prompt, file_urls, response_json_schema }) => {
        try {
          return await invokeAIDocumentPrompt({ prompt, file_urls, response_json_schema });
        } catch (error) {
          console.error('LLM invocation error:', error);
          throw error;
        }
      },
    },
  },
  agents: (() => {
    const convStore = {};
    const listeners = {};
    const notify = (id) => {
      (listeners[id] || []).forEach((fn) => {
        try { fn(convStore[id]); } catch {}
      });
    };
    return {
      createConversation: async ({ agent_name = 'InspectFlowBot', metadata = {} } = {}) => {
        const id = `conv_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
        convStore[id] = {
          id,
          agent_name,
          metadata,
          messages: [
            {
              role: 'assistant',
              content: `Hello ${metadata?.user_context || ''}! Ask me about inspections, IRC quality gates, ITP holds, or expediting status.`.trim(),
              created_at: new Date().toISOString(),
            },
          ],
        };
        return convStore[id];
      },
      getConversation: async (id) => convStore[id] || null,
      subscribeToConversation: (id, cb) => {
        listeners[id] = listeners[id] || [];
        listeners[id].push(cb);
        return () => {
          listeners[id] = (listeners[id] || []).filter((x) => x !== cb);
        };
      },
      addMessage: async (conv, msg) => {
        const id = typeof conv === 'string' ? conv : conv?.id;
        const c = convStore[id];
        if (!c) return null;
        c.messages.push({ ...msg, created_at: new Date().toISOString() });
        notify(id);
        try {
          const reply = await invokeAIDocumentPrompt({
            prompt: `You are InspectFlow Assistant. Answer concisely for EPC inspection & expediting context:\n\n${msg.content}`,
          });
          const answer = reply?.answer || reply?.text || reply?.summary || (typeof reply === 'string' ? reply : JSON.stringify(reply));
          c.messages.push({ role: 'assistant', content: answer, created_at: new Date().toISOString() });
        } catch {
          c.messages.push({
            role: 'assistant',
            content: 'AI assistant is currently unavailable. Use the Inspection / Expediting dashboards for live records.',
            created_at: new Date().toISOString(),
          });
        }
        notify(id);
        return c;
      },
    };
  })(),
};
