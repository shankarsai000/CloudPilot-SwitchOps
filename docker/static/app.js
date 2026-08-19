// CloudPilot AI Command Center OS Javascript (v2)

document.addEventListener("DOMContentLoaded", () => {
    // OS Elements & Settings
    const body = document.body;
    const themeToggleBtn = document.getElementById("theme-toggle");
    const scenarioSelect = document.getElementById("enterprise-select");
    const startScanBtn = document.getElementById("start-demo-btn");
    const storyModeBtn = document.getElementById("story-mode-btn");
    const runTwinSimulationBtn = document.getElementById("run-twin-simulation-btn");
    
    // Panels & Views
    const navItems = document.querySelectorAll(".nav-item");
    const tabPanels = document.querySelectorAll(".tab-panel");
    const liveActivityLog = document.getElementById("live-activity-log");
    
    // Copilot
    const copilotForm = document.getElementById("copilot-query-form");
    const copilotInput = document.getElementById("copilot-input-field");
    const copilotHistory = document.getElementById("copilot-chat-history");
    const suggestionChips = document.querySelectorAll(".suggestion-chip");
    
    // KPI metrics
    const kpiResources = document.getElementById("kpi-resources");
    const kpiCost = document.getElementById("kpi-cost");
    const kpiSavings = document.getElementById("kpi-savings");
    const kpiRisks = document.getElementById("kpi-risks");
    const kpiApps = document.getElementById("kpi-apps");
    const kpiConfidence = document.getElementById("kpi-confidence");

    // Telemetry Telemetry items
    const telemetryCpu = document.getElementById("telemetry-cpu");
    const telemetryCpuBar = document.getElementById("telemetry-cpu-bar");
    const telemetryMem = document.getElementById("telemetry-mem");
    const telemetryMemBar = document.getElementById("telemetry-mem-bar");
    const telemetryAvail = document.getElementById("telemetry-avail");
    const telemetryAvailBar = document.getElementById("telemetry-avail-bar");

    // Recommendations & Workspaces
    const recGrid = document.getElementById("recommendation-center-grid");
    const agentTabBtns = document.querySelectorAll(".agent-tab-btn");
    const workspaceBody = document.getElementById("agent-workspace-body");

    let activeProfile = "Startup";
    let isStoryRunning = false;
    let selectedGraphResource = null;

    // ═══════════════════════════════════════════════════════════════
    // 1. Theme Controller & Tab Controller
    // ═══════════════════════════════════════════════════════════════
    
    themeToggleBtn.addEventListener("click", () => {
        body.classList.toggle("light-theme");
        if (body.classList.contains("light-theme")) {
            themeToggleBtn.textContent = "Toggle Dark Mode";
        } else {
            themeToggleBtn.textContent = "Toggle Light Mode";
        }
    });

    navItems.forEach(item => {
        item.addEventListener("click", (e) => {
            e.preventDefault();
            navItems.forEach(n => n.classList.remove("active"));
            item.classList.add("active");
            
            const targetTab = item.getAttribute("data-tab");
            tabPanels.forEach(p => p.classList.remove("active"));
            
            const panel = document.getElementById(`tab-${targetTab}`);
            if (panel) {
                panel.classList.add("active");
                if (targetTab === "graph") {
                    renderInteractiveGraph();
                } else if (targetTab === "workspaces") {
                    const activeAgent = document.querySelector(".agent-tab-btn.active").getAttribute("data-agent");
                    renderAgentWorkspace(activeAgent);
                }
            }
        });
    });

    // Logging helper
    function logEvent(sender, text) {
        const time = new Date().toLocaleTimeString();
        const li = document.createElement("li");
        li.className = "feed-item";
        li.innerHTML = `
            <span class="feed-time">${time}</span>
            <strong style="color: var(--color-accent); min-width: 80px; display: inline-block;">${sender}</strong>
            <span class="feed-text">${text}</span>
        `;
        liveActivityLog.prepend(li);
    }

    // ═══════════════════════════════════════════════════════════════
    // 2. Scenario Data Selection & KPI
    // ═══════════════════════════════════════════════════════════════
    
    async function handleScenarioChange(profile) {
        activeProfile = profile;
        logEvent("SYSTEM", `Loading profile configuration '${profile}'...`);
        try {
            const res = await fetch("/api/demo/select", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ profile }),
            });
            const data = await res.json();
            if (data.status === "success") {
                const s = data.summary;
                kpiResources.textContent = s.resource_count;
                kpiCost.textContent = `$${s.monthly_cost_usd.toLocaleString()}`;
                
                // Static optimizations / savings details
                const savings = s.opportunities_count > 0 ? (s.monthly_cost_usd * 0.15) : 0;
                kpiSavings.textContent = `$${savings.toLocaleString(undefined, {maximumFractionDigits:0})}`;
                
                kpiRisks.textContent = profile === "Financial Services" ? "3" : (profile === "Healthcare" ? "2" : "1");
                kpiApps.textContent = s.application_count;
                
                logEvent("M1-IDA", `Successfully cataloged ${s.resource_count} resources and ${s.application_count} application boundaries.`);
                renderRecommendations();
                renderInteractiveGraph();
            }
        } catch (err) {
            console.error("Scenario load failed:", err);
        }
    }

    scenarioSelect.addEventListener("change", (e) => {
        handleScenarioChange(e.target.value);
    });

    // ═══════════════════════════════════════════════════════════════
    // 3. Topology Map Graph Rendering (SVG Canvas)
    // ═══════════════════════════════════════════════════════════════
    
    function renderInteractiveGraph() {
        const svg = document.getElementById("infra-svg");
        if (!svg) return;
        
        // Clear canvas
        svg.innerHTML = "";
        
        // Dynamic node positioning depending on active profile
        const nodes = [
            { id: "aws", type: "Provider", name: "AWS Cloud", x: 60, y: 220, color: "#ff9900" },
            { id: "vpc", type: "VPC", name: "Production VPC", x: 180, y: 220, color: "#10b981" },
            { id: "cluster", type: "Cluster", name: "EKS Cluster", x: 300, y: 220, color: "#6366f1" },
        ];

        if (activeProfile === "AI Startup" || activeProfile === "AI") {
            nodes.push(
                { id: "node-gpu-1", type: "EC2", name: "ml-gpu-training-1", x: 440, y: 120, cost: 4500, owner: "ML-Research", state: "RUNNING" },
                { id: "node-gpu-2", type: "EC2", name: "ml-gpu-training-2", x: 440, y: 220, cost: 4500, owner: "ML-Research", state: "RUNNING" },
                { id: "node-gpu-3", type: "EC2", name: "ml-gpu-training-3", x: 440, y: 320, cost: 4500, owner: "ML-Research", state: "RUNNING" }
            );
        } else if (activeProfile === "Healthcare") {
            nodes.push(
                { id: "node-ehr", type: "RDS", name: "ehr-patient-db", x: 440, y: 150, cost: 2800, owner: "Clinical-IT", state: "RUNNING" },
                { id: "node-video", type: "EC2", name: "video-transcoder", x: 440, y: 290, cost: 600, owner: "Comm-Ops", state: "RUNNING" }
            );
        } else {
            // Default Startup/Standard
            nodes.push(
                { id: "node-web", type: "EC2", name: "web-server", x: 440, y: 120, cost: 80, owner: "Frontend", state: "RUNNING" },
                { id: "node-db", type: "RDS", name: "users-db", x: 440, y: 220, cost: 450, owner: "Database", state: "RUNNING" },
                { id: "node-auth", type: "EC2", name: "auth-server", x: 440, y: 320, cost: 150, owner: "SecOps", state: "RUNNING" }
            );
        }

        // Draw connections
        for (let i = 0; i < nodes.length; i++) {
            const n = nodes[i];
            if (n.type === "EC2" || n.type === "RDS") {
                const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
                line.setAttribute("x1", 300);
                line.setAttribute("y1", 220);
                line.setAttribute("x2", n.x);
                line.setAttribute("y2", n.y);
                line.setAttribute("class", "node-line");
                svg.appendChild(line);
            } else if (i > 0 && i < 3) {
                const prev = nodes[i-1];
                const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
                line.setAttribute("x1", prev.x);
                line.setAttribute("y1", prev.y);
                line.setAttribute("x2", n.x);
                line.setAttribute("y2", n.y);
                line.setAttribute("class", "node-line");
                svg.appendChild(line);
            }
        }

        // Draw nodes
        nodes.forEach(n => {
            const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
            g.setAttribute("class", "node-group");
            g.addEventListener("click", () => showResourceDetails(n));

            const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
            circle.setAttribute("cx", n.x);
            circle.setAttribute("cy", n.y);
            circle.setAttribute("r", n.type === "Provider" ? 25 : 18);
            circle.setAttribute("fill", n.color || "#3b82f6");
            circle.setAttribute("stroke", "rgba(255,255,255,0.2)");
            circle.setAttribute("stroke-width", "2");
            g.appendChild(circle);

            const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
            text.setAttribute("x", n.x);
            text.setAttribute("y", n.y + 35);
            text.setAttribute("fill", "var(--text-primary)");
            text.setAttribute("font-size", "11px");
            text.setAttribute("font-weight", "600");
            text.setAttribute("text-anchor", "middle");
            text.textContent = n.name;
            g.appendChild(text);

            svg.appendChild(g);
        });
    }

    function showResourceDetails(node) {
        const inspector = document.getElementById("graph-details-panel");
        if (!inspector) return;

        if (node.type === "Provider" || node.type === "VPC" || node.type === "Cluster") {
            inspector.innerHTML = `
                <h3 class="panel-subtitle">${node.name}</h3>
                <div class="empty-state" style="margin-top: 10px;">Select a leaf resource node (EC2/RDS) to inspect specific details.</div>
            `;
            return;
        }

        selectedGraphResource = node.id;
        inspector.innerHTML = `
            <h3 class="panel-subtitle" style="margin-bottom: 15px;">${node.name}</h3>
            <div style="font-size: 13px; display: flex; flex-direction: column; gap: 8px;">
                <div><strong>Type:</strong> ${node.type}</div>
                <div><strong>Cloud:</strong> AWS</div>
                <div><strong>Monthly Cost:</strong> $${node.cost}/mo</div>
                <div><strong>Owner Team:</strong> ${node.owner}</div>
                <div><strong>State:</strong> <span style="color: var(--color-success)">${node.state}</span></div>
                <div style="margin-top: 10px; border-top: 1px solid var(--border-color); padding-top: 10px;">
                    <strong>Recommended Actions:</strong>
                    <div style="color: var(--color-warning); font-size: 11px; margin-top: 5px;">
                        💡 Optimization target identified in M5 Strategy loop. Run Story Mode to evaluate.
                    </div>
                </div>
            </div>
        `;
    }

    // ═══════════════════════════════════════════════════════════════
    // 4. Recommendation Center Center Grid
    // ═══════════════════════════════════════════════════════════════
    
    function renderRecommendations(sortBy = "savings") {
        recGrid.innerHTML = "";
        let recs = [];

        // Build mock recommendations database
        if (activeProfile === "Startup") {
            recs = [
                { id: "1", type: "Oversized Database", target: "rds-db-1", savings: 150, risk: "MEDIUM", confidence: 94, app: "User Database", impact: "Saves 33% DB spend", readiness: "READY" },
                { id: "2", type: "Underutilized Instance", target: "ec2-auth-1", savings: 50, risk: "LOW", confidence: 91, app: "Authentication", impact: "Saves 20% Auth compute", readiness: "READY" },
            ];
        } else if (activeProfile === "AI Startup" || activeProfile === "AI") {
            recs = [
                { id: "1", type: "Idle GPU Cluster Node", target: "ec2-gpu-node-4", savings: 4500, risk: "HIGH", confidence: 95, app: "LLM Model Training", impact: "Saves 100% cost of idle node", readiness: "EXECUTIVE_APPROVAL_REQUIRED" },
            ];
        } else if (activeProfile === "Healthcare") {
            recs = [
                { id: "1", type: "Oversized HIPAA DB", target: "rds-ehr-db", savings: 800, risk: "HIGH", confidence: 97, app: "Electronic Health Records", impact: "Optimizes patient IOPS limits", readiness: "SECURITY_APPROVAL_REQUIRED" },
            ];
        } else {
            recs = [
                { id: "1", type: "Idle Instance Scale-Down", target: "compute-node-1", savings: 1200, risk: "MEDIUM", confidence: 92, app: "Core API", impact: "Saves compute waste", readiness: "READY" },
            ];
        }

        // Sort items
        recs.sort((a, b) => {
            if (sortBy === "savings") return b.savings - a.savings;
            if (sortBy === "confidence") return b.confidence - a.confidence;
            if (sortBy === "risk") {
                const riskMap = { "LOW": 1, "MEDIUM": 2, "HIGH": 3 };
                return riskMap[b.risk] - riskMap[a.risk];
            }
            return 0;
        });

        recs.forEach(r => {
            const card = document.createElement("div");
            card.className = "recommendation-card";
            card.innerHTML = `
                <div class="rec-header">
                    <span class="rec-title">${r.type}</span>
                    <span class="rec-savings">+$${r.savings.toLocaleString()}/mo</span>
                </div>
                <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 12px;">
                    Target: <code>${r.target}</code> &middot; Affected Application: <strong>${r.app}</strong>
                </div>
                <div style="font-size: 11px; margin-bottom: 10px; color: var(--text-muted)">
                    Business Impact: ${r.impact}
                </div>
                <div class="rec-meta" style="border-top: 1px solid var(--border-color); padding-top: 8px;">
                    <span>Risk: <strong style="color: var(--color-warning)">${r.risk}</strong></span>
                    <span>Confidence: <strong>${r.confidence}%</strong></span>
                    <span>Status: <strong style="color: var(--color-success)">${r.readiness}</strong></span>
                </div>
            `;
            recGrid.appendChild(card);
        });
    }

    document.querySelectorAll(".sort-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".sort-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            renderRecommendations(btn.getAttribute("data-sort"));
        });
    });

    // ═══════════════════════════════════════════════════════════════
    // 5. Guided Story Mode & AI Processing Timeline
    // ═══════════════════════════════════════════════════════════════
    
    async function triggerScan() {
        if (isStoryRunning) return;
        isStoryRunning = true;
        startScanBtn.disabled = true;
        startScanBtn.textContent = "Scanning...";
        logEvent("SYSTEM", "AI pipeline triggered manually. Analyzing telemetry & resources...");

        await fetch("/api/demo/pipeline-start", { method: "POST" });

        const interval = setInterval(async () => {
            const res = await fetch("/api/demo/pipeline-status");
            const status = await res.json();
            let active = false;

            for (const [mod, state] of Object.entries(status)) {
                const el = document.querySelector(`.pipeline-step[data-step="${mod}"]`);
                if (el) {
                    const statusText = el.querySelector(".step-status");
                    el.classList.remove("pending", "running", "completed");
                    if (state === "COMPLETED") {
                        el.classList.add("completed");
                        statusText.textContent = "Completed";
                    } else if (state === "RUNNING") {
                        el.classList.add("running");
                        statusText.textContent = "Processing...";
                        active = true;
                    } else {
                        el.classList.add("pending");
                        statusText.textContent = "Idle";
                    }
                }
            }

            if (!active) {
                clearInterval(interval);
                isStoryRunning = false;
                startScanBtn.disabled = false;
                startScanBtn.textContent = "Scan Environment";
                logEvent("SYSTEM", "Pipeline execution finished successfully.");
            }
        }, 600);
    }

    startScanBtn.addEventListener("click", () => {
        triggerScan();
    });

    // Guided Story Mode Tour
    storyModeBtn.addEventListener("click", () => {
        if (isStoryRunning) return;
        isStoryRunning = true;
        storyModeBtn.disabled = true;
        storyModeBtn.textContent = "Tour Active...";
        logEvent("STORY-MODE", "Guided story mode activated. Performing end-to-end cloud operations tour...");

        let step = 0;
        const tourSteps = [
            { sender: "M1-IDA", text: "Discovered production subnets and cataloged VPC dependencies." },
            { sender: "M2-CIA", text: "Ingested Billing records. Identified $4,500 underutilized ML nodes." },
            { sender: "M3-AIA", text: "Mapped Model Inference API boundary and discovered 1 active dependency cycle." },
            { sender: "M4-RIA", text: "Analyzed blast radius of compute resizing. Predicted 0% SLA failure probability." },
            { sender: "M5-SA", text: "Generated optimization strategies. Created EC2 resize recommendation." },
            { sender: "M6-DTS", text: "Constructed digital twin copy. Simulated workload performance." },
            { sender: "M7-EE", text: "Generated explainability audit records. Drafted decision reasoning plan." },
            { sender: "M9-DE", text: "Decision Council reached majority consensus: APPROVE." },
            { sender: "M10-AEA", text: "Executed safe scaling changes and locked resources. Telemetry verified healthy." }
        ];

        const timelineSteps = [
            "M1_IDA", "M2_CIA", "M3_AIA", "M4_RIA", "M5_SA", "M6_DTS", "M7_EE", "M8_LEA", "M9_DE", "M10_AEA"
        ];

        const tourInterval = setInterval(() => {
            if (step < tourSteps.length) {
                const s = tourSteps[step];
                logEvent(s.sender, s.text);
                
                // Highlight step in timeline
                const activeMod = timelineSteps[step];
                const el = document.querySelector(`.pipeline-step[data-step="${activeMod}"]`);
                if (el) {
                    el.classList.add("completed");
                    el.querySelector(".step-status").textContent = "Completed";
                }

                step++;
            } else {
                clearInterval(tourInterval);
                isStoryRunning = false;
                storyModeBtn.disabled = false;
                storyModeBtn.textContent = "Start Story Mode Tour";
                logEvent("STORY-MODE", "Guided tour completed. Savings harvested successfully.");
            }
        }, 1200);
    });

    // ═══════════════════════════════════════════════════════════════
    // 6. Digital Twin Simulated Run
    // ═══════════════════════════════════════════════════════════════
    
    runTwinSimulationBtn.addEventListener("click", () => {
        logEvent("M6-DTS", "Constructing Virtual Digital Twin copy...");
        document.querySelectorAll(".twin-step").forEach(el => el.classList.remove("active", "completed"));
        
        let step = 1;
        const simInterval = setInterval(() => {
            const stepEl = document.getElementById(`twin-step-${step}`);
            if (stepEl) {
                stepEl.classList.add("active");
                if (step > 1) {
                    document.getElementById(`twin-step-${step-1}`).classList.remove("active");
                    document.getElementById(`twin-step-${step-1}`).classList.add("completed");
                }
                step++;
            } else {
                clearInterval(simInterval);
                document.getElementById("twin-step-4").classList.remove("active");
                document.getElementById("twin-step-4").classList.add("completed");
                logEvent("M6-DTS", "Digital Twin simulation completed. No failures predicted under load tests.");
            }
        }, 800);
    });

    // ═══════════════════════════════════════════════════════════════
    // 7. Workspaces Tab Controller
    // ═══════════════════════════════════════════════════════════════
    
    agentTabBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            agentTabBtns.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            renderAgentWorkspace(btn.getAttribute("data-agent"));
        });
    });

    function renderAgentWorkspace(agent) {
        if (agent === "infra") {
            workspaceBody.innerHTML = `
                <h3 class="panel-subtitle">Discovery Workspace (M1)</h3>
                <div style="font-size: 13px; display: flex; flex-direction: column; gap: 10px; margin-top: 15px;">
                    <div><strong>Scanner Workers:</strong> 4 parallel threads</div>
                    <div><strong>Discovery Adapters:</strong> AWS, GCP, Azure, Kubernetes</div>
                    <div><strong>Discovery Cycle:</strong> Every 5 minutes</div>
                    <div style="margin-top: 10px; border-top: 1px solid var(--border-color); padding-top: 10px;">
                        <strong>Target Scanned Objects:</strong>
                        <pre style="background: rgba(0,0,0,0.2); padding: 10px; border-radius: 6px; margin-top: 5px; font-family: var(--font-mono); font-size:11px;">
{
  "provider": "AWS",
  "regions": ["us-east-1", "eu-west-1"],
  "resources_found": ${activeProfile === "Startup" ? 5 : 20}
}</pre>
                    </div>
                </div>
            `;
        } else if (agent === "cost") {
            workspaceBody.innerHTML = `
                <h3 class="panel-subtitle">Cost Intelligence Workspace (M2)</h3>
                <div style="font-size: 13px; display: flex; flex-direction: column; gap: 10px; margin-top: 15px;">
                    <div><strong>Correlator Accuracy:</strong> 94.2% matching rate</div>
                    <div><strong>Spike Anomaly Threshold:</strong> 30.0% standard deviation</div>
                    <div><strong>Forecasting Period:</strong> 7 / 14 / 30 / 90 / 365 Days</div>
                    <div style="margin-top: 10px; border-top: 1px solid var(--border-color); padding-top: 10px;">
                        <strong>Billing Ingestion Logs:</strong>
                        <div style="font-family: var(--font-mono); font-size: 11px; color: var(--color-success); margin-top: 5px;">
                            ✓ Ingested AWS Cost Explorer daily payload.<br>
                            ✓ Correlated billing items to EC2 compute targets.
                        </div>
                    </div>
                </div>
            `;
        } else if (agent === "app") {
            workspaceBody.innerHTML = `
                <h3 class="panel-subtitle">Application Intelligence Workspace (M3)</h3>
                <div style="font-size: 13px; display: flex; flex-direction: column; gap: 10px; margin-top: 15px;">
                    <div><strong>Discovered Mappings:</strong> Tag-based, naming convention, namespace boundaries</div>
                    <div><strong>Criticality Scoring:</strong> Business priority weightings</div>
                    <div><strong>Active Cycles:</strong> 0 dependency loops detected</div>
                </div>
            `;
        } else if (agent === "risk") {
            workspaceBody.innerHTML = `
                <h3 class="panel-subtitle">Risk Intelligence Workspace (M4)</h3>
                <div style="font-size: 13px; display: flex; flex-direction: column; gap: 10px; margin-top: 15px;">
                    <div><strong>SPOF Scan Status:</strong> Clean (no single point of failure)</div>
                    <div><strong>Blast Radius Prediction:</strong> Low blast radius on target resizing</div>
                    <div><strong>Validation Probability:</strong> 99.4% confidence score</div>
                </div>
            `;
        } else if (agent === "council") {
            // Decision Council voting table
            workspaceBody.innerHTML = `
                <h3 class="panel-subtitle">Decision Council (M9) - Collaborative Votes</h3>
                <table class="council-voting-table">
                    <thead>
                        <tr>
                            <th>Agent Module</th>
                            <th>Vote Verdict</th>
                            <th>Confidence</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td>Infrastructure Agent (M1)</td>
                            <td><span class="vote-badge approve">APPROVE</span></td>
                            <td>98%</td>
                        </tr>
                        <tr>
                            <td>Cost Intelligence (M2)</td>
                            <td><span class="vote-badge approve">APPROVE</span></td>
                            <td>95%</td>
                        </tr>
                        <tr>
                            <td>Risk Intelligence (M4)</td>
                            <td><span class="vote-badge approve">${activeProfile === "Banking" ? "CONDITIONAL" : "APPROVE"}</span></td>
                            <td>92%</td>
                        </tr>
                        <tr>
                            <td>Digital Twin Simulator (M6)</td>
                            <td><span class="vote-badge approve">APPROVE</span></td>
                            <td>97%</td>
                        </tr>
                        <tr>
                            <td>Learning Agent (M8)</td>
                            <td><span class="vote-badge approve">APPROVE</span></td>
                            <td>94%</td>
                        </tr>
                    </tbody>
                </table>
                <div style="margin-top: 15px; font-size: 12px; color: var(--text-secondary)">
                    <strong>Final Status:</strong> <span style="color: var(--color-success); font-weight:700;">APPROVED BY CONSENSUS</span>
                </div>
            `;
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // 8. Copilot Chatbot Handler
    // ═══════════════════════════════════════════════════════════════
    
    async function handleCopilotSubmit(query) {
        if (!query.trim()) return;

        // User balloon
        const userDiv = document.createElement("div");
        userDiv.className = "copilot-message user";
        userDiv.textContent = query;
        copilotHistory.appendChild(userDiv);
        copilotInput.value = "";
        copilotHistory.scrollTop = copilotHistory.scrollHeight;

        // Wait balloon
        const agentDiv = document.createElement("div");
        agentDiv.className = "copilot-message agent";
        agentDiv.textContent = "...";
        copilotHistory.appendChild(agentDiv);
        copilotHistory.scrollTop = copilotHistory.scrollHeight;

        try {
            const res = await fetch("/api/demo/copilot", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ query }),
            });
            const data = await res.json();
            
            // Type response
            agentDiv.innerHTML = data.response;
            copilotHistory.scrollTop = copilotHistory.scrollHeight;
        } catch (err) {
            agentDiv.textContent = "Sorry, I encountered an issue querying the agent stack.";
        }
    }

    copilotForm.addEventListener("submit", (e) => {
        e.preventDefault();
        handleCopilotSubmit(copilotInput.value);
    });

    suggestionChips.forEach(chip => {
        chip.addEventListener("click", () => {
            handleCopilotSubmit(chip.textContent);
        });
    });

    // ═══════════════════════════════════════════════════════════════
    // 9. Startup & Telemetry loop
    // ═══════════════════════════════════════════════════════════════
    
    // Live telemetry update simulation loop
    setInterval(async () => {
        try {
            const res = await fetch(`/api/demo/telemetry?target_id=${selectedResource}`);
            const data = await res.json();
            
            telemetryCpu.textContent = `${data.cpu_percent}%`;
            telemetryCpuBar.style.width = `${data.cpu_percent}%`;

            telemetryMem.textContent = `${data.memory_percent}%`;
            telemetryMemBar.style.width = `${data.memory_percent}%`;

            const availPercent = data.availability * 100;
            telemetryAvail.textContent = `${availPercent}%`;
            telemetryAvailBar.style.width = `${availPercent}%`;
        } catch (err) {
            // fail silently
        }
    }, 2500);

    // Bootstrap
    handleScenarioChange("Startup");
});
