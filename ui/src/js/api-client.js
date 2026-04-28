// Research API Client
// Handles communication with FastAPI backend

async function authHeaders() {
    // window.getIdToken is provided by ui/src/js/auth.js. If it's missing
    // (auth.js failed to load) we still send the request so the user gets
    // a clean 401 from the server rather than a JS error in the console.
    if (typeof window === 'undefined' || typeof window.getIdToken !== 'function') {
        return {};
    }
    try {
        const token = await window.getIdToken();
        return { 'Authorization': `Bearer ${token}` };
    } catch (_) {
        return {};
    }
}

class ResearchClient {
    constructor(baseUrl = 'http://localhost:8233') {
        this.baseUrl = baseUrl;
        this.workflowId = null;
        this.eventSource = null;
    }

    async startResearch(query) {
        const response = await fetch(`${this.baseUrl}/api/start-research`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(await authHeaders()),
            },
            body: JSON.stringify({ query })
        });

        if (!response.ok) {
            throw new Error('Failed to start research');
        }

        const data = await response.json();
        this.workflowId = data.workflow_id;
        return data;
    }

    async initializeResearch(query, workflowId) {
        const response = await fetch(`${this.baseUrl}/api/initialize/${workflowId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(await authHeaders()),
            },
            body: JSON.stringify({ query })
        });

        if (!response.ok) {
            throw new Error('Failed to initialize research');
        }

        return await response.json();
    }

    async getStatus(workflowId = null) {
        const id = workflowId || this.workflowId;
        if (!id) {
            throw new Error('No workflow ID available');
        }

        const response = await fetch(`${this.baseUrl}/api/status/${id}`, {
            headers: { ...(await authHeaders()) },
        });

        if (!response.ok) {
            throw new Error('Failed to get status');
        }

        return await response.json();
    }

    async submitAnswer(answer, workflowId = null, currentQuestionIndex = 0) {
        const id = workflowId || this.workflowId;
        if (!id) {
            throw new Error('No workflow ID available');
        }

        const response = await fetch(`${this.baseUrl}/api/answer/${id}/${currentQuestionIndex}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(await authHeaders()),
            },
            body: JSON.stringify({ answer })
        });

        if (!response.ok) {
            throw new Error('Failed to submit answer');
        }

        return await response.json();
    }

    async getResult(workflowId = null) {
        const id = workflowId || this.workflowId;
        if (!id) {
            throw new Error('No workflow ID available');
        }

        const response = await fetch(`${this.baseUrl}/api/result/${id}`, {
            headers: { ...(await authHeaders()) },
        });

        if (!response.ok) {
            throw new Error('Result not ready or failed');
        }

        return await response.json();
    }

    // Server-Sent Events for live updates.
    // NOTE: EventSource cannot send Authorization headers. When the backend
    // /api/stream endpoint is implemented, switch to a query-string token or
    // a fetch + ReadableStream so this stays authenticated.
    streamStatus(workflowId, onUpdate, onComplete, onError) {
        const id = workflowId || this.workflowId;
        if (!id) {
            throw new Error('No workflow ID available');
        }

        this.eventSource = new EventSource(`${this.baseUrl}/api/stream/${id}`);
        
        this.eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            onUpdate(data);
            
            if (data.status === 'complete') {
                this.closeStream();
                if (onComplete) onComplete(data);
            }
        };

        this.eventSource.onerror = (error) => {
            console.error('Stream error:', error);
            this.closeStream();
            if (onError) onError(error);
        };
    }

    closeStream() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
    }

    // Polling alternative (if SSE not preferred)
    async pollStatus(workflowId, onUpdate, interval = 2000) {
        const id = workflowId || this.workflowId;
        
        const poll = async () => {
            try {
                const status = await this.getStatus(id);
                onUpdate(status);
                
                if (status.status !== 'complete' && status.status !== 'failed') {
                    setTimeout(poll, interval);
                }
            } catch (error) {
                console.error('Polling error:', error);
            }
        };

        poll();
    }
}

// Export for use in HTML
if (typeof window !== 'undefined') {
    window.ResearchClient = ResearchClient;
}
