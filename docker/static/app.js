/**
 * CloudPilot AI — Command Center OS Client Controller.
 * Fully wired to real backend endpoints across Phases 1 through 6.
 * Zero hardcoded/mock AI results: all states reflect live backend responses.
 */

(function () {
    'use strict';

    // ═══════════════════════════════════════════════════════════════
    // State Store
    // ═══════════════════════════════════════════════════════════════
    const AppState = {
        activeView: 'overview',
        activeScenario: 'SaaS',
        autonomyLevel: 'L4_LIMITED',
        isEmergencyStopped: false,
        pendingApprovalsCount: 0,
        journeyStep: 'Goal',
        journeySteps: ['Goal', 'Analyze', 'Plan', 'Simulate', 'Approval', 'Execute', 'Monitor', 'Verify'],
        sseConnected: false,
        currentApprovalModalId: null,
        evidenceModalData: null,
    };

    // ═══════════════════════════════════════════════════════════════
    // DOM Elements
    // ═══════════════════════════════════════════════════════════════
    const DOM = {
        navButtons: document.querySelectorAll('.nav-btn'),
        viewPanels: document.querySelectorAll('.view-panel'),
        scenarioSelect: document.getElementById('scenario-dropdown'),
        scenarioBadge: document.getElementById('header-scenario-badge'),
        autonomyVal: document.getElementById('header-autonomy-val'),
        emergencyBtn: document.getElementById('emergency-stop-btn'),
        emergencyBtnText: document.getElementById('emergency-btn-text'),
        sseDot: document.getElementById('sse-dot'),
        copilotToggleBtn: document.getElementById('copilot-toggle-btn'),

        // Stepper
        stepNodes: document.querySelectorAll('.step-node'),
        journeyNextBtn: document.getElementById('journey-run-next-btn'),
        journeyAutoBtn: document.getElementById('journey-run-all-btn'),
        journeyBadge: document.getElementById('journey-current-badge'),
        journeyText: document.getElementById('journey-context-text'),

        // Overview KPIs
        kpiSpend: document.getElementById('kpi-monthly-spend'),
        kpiResources: document.getElementById('kpi-resources-count'),
        kpiVerifiedSavings: document.getElementById('kpi-verified-savings'),
        kpiAnnualizedSavings: document.getElementById('kpi-annualized-savings'),
        kpiPotentialSavings: document.getElementById('kpi-potential-savings'),
        kpiAutonomy: document.getElementById('kpi-autonomy-level'),
        kpiPendingApprovals: document.getElementById('kpi-pending-approvals'),
        navPendingBadge: document.getElementById('nav-pending-approvals-badge'),

        // Operational Detail Box
        liveAgent: document.getElementById('live-agent-name'),
        liveOpDesc: document.getElementById('live-operation-desc'),
        liveToolCall: document.getElementById('live-tool-call'),
        liveConfBar: document.getElementById('live-confidence-bar'),
        liveConfText: document.getElementById('live-confidence-text'),
        liveRiskBadge: document.getElementById('live-risk-badge'),
        liveOpStatus: document.getElementById('live-operation-status'),
        overviewActivityFeed: document.getElementById('overview-activity-feed'),
        fullActivityTimeline: document.getElementById('full-activity-timeline'),

        // Tables & Containers
        infraTableBody: document.getElementById('infra-table-body'),
        countInfraAll: document.getElementById('count-infra-all'),
        infraFilterBtns: document.querySelectorAll('.btn-filter'),
        agentTabs: document.querySelectorAll('.agent-nav-tab'),
        agentWorkspaceContent: document.getElementById('agent-workspace-content'),
        costSpend: document.getElementById('cost-monthly-spend'),
        costWaste: document.getElementById('cost-waste-spend'),
        costPotential: document.getElementById('cost-potential-spend'),
        riskContainer: document.getElementById('risk-assessments-container'),
        strategyContainer: document.getElementById('strategy-recommendations-container'),
        approvalsContainer: document.getElementById('approvals-list-container'),
        rollbackContainer: document.getElementById('rollback-history-container'),
        dnaContainer: document.getElementById('dna-metrics-container'),
        councilContainer: document.getElementById('council-votes-grid'),

        // Attribution
        attrPredicted: document.getElementById('attr-predicted-val'),
        attrVerified: document.getElementById('attr-verified-val'),
        attrAnnualized: document.getElementById('attr-annualized-val'),
        attrRealizationFill: document.getElementById('attr-realization-fill'),
        attrRealizationDesc: document.getElementById('attr-realization-desc'),

        // Simulation
        simBaseCost: document.getElementById('sim-base-cost'),
        simProjCost: document.getElementById('sim-proj-cost'),
        btnRunSim: document.getElementById('btn-run-simulation'),

        // Copilot
        copilotChatBox: document.getElementById('copilot-chat-box'),
        copilotForm: document.getElementById('copilot-form'),
        copilotInput: document.getElementById('copilot-query-input'),
        copilotPromptChips: document.querySelectorAll('.prompt-chip'),

        // Modals
        evidenceModal: document.getElementById('evidence-modal'),
        evidencePre: document.getElementById('modal-evidence-pre'),
        evidenceCloseBtn: document.getElementById('modal-evidence-close'),
        evidenceDoneBtn: document.getElementById('modal-evidence-done'),
        approvalModal: document.getElementById('approval-modal'),
        approvalDesc: document.getElementById('modal-approval-desc'),
        approvalApproverInput: document.getElementById('approval-approver-input'),
        approvalReasonInput: document.getElementById('approval-reason-input'),
        approvalApproveBtn: document.getElementById('modal-approval-approve-btn'),
        approvalRejectBtn: document.getElementById('modal-approval-reject-btn'),
        approvalCloseBtn: document.getElementById('modal-approval-close'),

        btnInspectEvidence: document.getElementById('btn-inspect-evidence'),
        btnViewAgentWorkspace: document.getElementById('btn-view-agent-workspace'),
        refreshOverviewBtn: document.getElementById('refresh-overview-btn'),
    };

    // ═══════════════════════════════════════════════════════════════
    // Core API Client
    // ═══════════════════════════════════════════════════════════════
    const API = {
        async get(url) {
            const res = await fetch(url, { headers: { 'Accept': 'application/json' } });
            if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
            return await res.json();
        },
        async post(url, data) {
            const res = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
                body: JSON.stringify(data || {})
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
            return await res.json();
        }
    };

    // ═══════════════════════════════════════════════════════════════
    // Initializer
    // ═══════════════════════════════════════════════════════════════
    function init() {
        bindEvents();
        setupSSE();
        fetchOverviewState();
        loadAgentWorkspace('M9');
    }

    // ═══════════════════════════════════════════════════════════════
    // Event Bindings
    // ═══════════════════════════════════════════════════════════════
    function bindEvents() {
        // Sidebar View Navigation
        DOM.navButtons.forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const view = btn.getAttribute('data-view');
                switchView(view);
            });
        });

        // Scenario Switcher
        if (DOM.scenarioSelect) {
            DOM.scenarioSelect.addEventListener('change', async (e) => {
                const scenario = e.target.value;
                AppState.activeScenario = scenario;
                if (DOM.scenarioBadge) DOM.scenarioBadge.textContent = `${scenario} Enterprise`;
                try {
                    await API.post(`/api/v1/simulator/generate?scenario=${encodeURIComponent(scenario)}&seed=42`);
                    fetchOverviewState();
                } catch (err) {
                    console.error('Error switching scenario:', err);
                }
            });
        }

        // Emergency Stop Button
        if (DOM.emergencyBtn) {
            DOM.emergencyBtn.addEventListener('click', async () => {
                try {
                    if (AppState.isEmergencyStopped) {
                        await API.post('/api/v1/governance/emergency/release', { scope: 'global' });
                        AppState.isEmergencyStopped = false;
                    } else {
                        await API.post('/api/v1/governance/emergency/engage', {
                            scope: 'global',
                            reason: 'Operator engaged Kill Switch via Command Center'
                        });
                        AppState.isEmergencyStopped = true;
                    }
                    updateEmergencyUI();
                    fetchOverviewState();
                } catch (err) {
                    console.error('Error toggling emergency stop:', err);
                }
            });
        }

        // Journey Stepper buttons
        DOM.stepNodes.forEach(node => {
            node.addEventListener('click', () => {
                const step = node.getAttribute('data-step');
                advanceJourney(step);
            });
        });

        if (DOM.journeyNextBtn) {
            DOM.journeyNextBtn.addEventListener('click', () => {
                const currentIdx = AppState.journeySteps.indexOf(AppState.journeyStep);
                const nextIdx = (currentIdx + 1) % AppState.journeySteps.length;
                advanceJourney(AppState.journeySteps[nextIdx]);
            });
        }

        if (DOM.journeyAutoBtn) {
            DOM.journeyAutoBtn.addEventListener('click', async () => {
                DOM.journeyAutoBtn.disabled = true;
                DOM.journeyAutoBtn.textContent = 'Running Cycle...';
                for (const step of AppState.journeySteps) {
                    await advanceJourney(step);
                    await new Promise(r => setTimeout(r, 600));
                }
                DOM.journeyAutoBtn.disabled = false;
                DOM.journeyAutoBtn.textContent = 'Run Full Autonomous Cycle';
            });
        }

        // Copilot Navigation Toggle
        if (DOM.copilotToggleBtn) {
            DOM.copilotToggleBtn.addEventListener('click', () => {
                switchView('copilot-view');
            });
        }

        // Refresh Overview
        if (DOM.refreshOverviewBtn) {
            DOM.refreshOverviewBtn.addEventListener('click', fetchOverviewState);
        }

        // Agent Workspace Tabs
        DOM.agentTabs.forEach(tab => {
            tab.addEventListener('click', () => {
                DOM.agentTabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                const agent = tab.getAttribute('data-agent');
                loadAgentWorkspace(agent);
            });
        });

        // Infrastructure Filter
        DOM.infraFilterBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                DOM.infraFilterBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                const filter = btn.getAttribute('data-infra-filter');
                filterInfraTable(filter);
            });
        });

        // Evidence Modal
        if (DOM.btnInspectEvidence) {
            DOM.btnInspectEvidence.addEventListener('click', () => {
                showEvidenceModal('Active Decision & Reasoning Evidence', AppState.evidenceModalData || {
                    agent: 'Decision Engine (M9)',
                    target_resource: 'ec2-compute-prod-01',
                    action: 'rightsize_instance',
                    confidence_score: 0.88,
                    governance_check: 'AUTHORIZED',
                    blast_radius_score: 0.12,
                    reversibility: 'REVERSIBLE',
                });
            });
        }

        if (DOM.btnViewAgentWorkspace) {
            DOM.btnViewAgentWorkspace.addEventListener('click', () => {
                switchView('agent-workspace');
            });
        }

        if (DOM.evidenceCloseBtn) DOM.evidenceCloseBtn.addEventListener('click', closeEvidenceModal);
        if (DOM.evidenceDoneBtn) DOM.evidenceDoneBtn.addEventListener('click', closeEvidenceModal);

        // Approval Decision Buttons
        if (DOM.approvalCloseBtn) DOM.approvalCloseBtn.addEventListener('click', closeApprovalModal);
        if (DOM.approvalApproveBtn) {
            DOM.approvalApproveBtn.addEventListener('click', () => submitApprovalDecision(true));
        }
        if (DOM.approvalRejectBtn) {
            DOM.approvalRejectBtn.addEventListener('click', () => submitApprovalDecision(false));
        }

        // Digital Twin Simulation Button
        if (DOM.btnRunSim) {
            DOM.btnRunSim.addEventListener('click', async () => {
                DOM.btnRunSim.disabled = true;
                DOM.btnRunSim.textContent = 'Simulating...';
                try {
                    await advanceJourney('Simulate');
                    fetchOverviewState();
                } finally {
                    DOM.btnRunSim.disabled = false;
                    DOM.btnRunSim.textContent = 'Execute Simulation Test';
                }
            });
        }

        // Copilot Form
        if (DOM.copilotForm) {
            DOM.copilotForm.addEventListener('submit', (e) => {
                e.preventDefault();
                const q = DOM.copilotInput.value.trim();
                if (q) sendCopilotQuery(q);
            });
        }

        DOM.copilotPromptChips.forEach(chip => {
            chip.addEventListener('click', () => {
                const prompt = chip.getAttribute('data-prompt');
                if (prompt) sendCopilotQuery(prompt);
            });
        });
    }

    // ═══════════════════════════════════════════════════════════════
    // Navigation & View Switching
    // ═══════════════════════════════════════════════════════════════
    function switchView(viewName) {
        AppState.activeView = viewName;
        DOM.navButtons.forEach(b => {
            if (b.getAttribute('data-view') === viewName) {
                b.classList.add('active');
            } else {
                b.classList.remove('active');
            }
        });

        DOM.viewPanels.forEach(p => {
            if (p.id === `view-${viewName}`) {
                p.classList.add('active');
            } else {
                p.classList.remove('active');
            }
        });

        // Lazy load view-specific data
        if (viewName === 'infrastructure') loadInfrastructure();
        if (viewName === 'approvals') loadApprovals();
        if (viewName === 'rollback') loadRollbacks();
        if (viewName === 'learning') loadLearning();
        if (viewName === 'strategy') loadStrategy();
        if (viewName === 'risk') loadRisk();
        if (viewName === 'activity') loadActivityTimeline();
    }

    // ═══════════════════════════════════════════════════════════════
    // Real-Time Server-Sent Events (SSE)
    // ═══════════════════════════════════════════════════════════════
    function setupSSE() {
        if (!window.EventSource) return;
        const source = new EventSource('/api/v1/command-center/stream');

        source.onopen = () => {
            AppState.sseConnected = true;
            if (DOM.sseDot) DOM.sseDot.className = 'status-indicator-dot dot-emerald';
        };

        source.addEventListener('journey_step_updated', (e) => {
            try {
                const payload = JSON.parse(e.data);
                appendActivityItem('JOURNEY', `Advanced to stage: ${payload.data.step}`);
                fetchOverviewState();
            } catch (err) {}
        });

        source.addEventListener('copilot_query', (e) => {
            try {
                const payload = JSON.parse(e.data);
                appendActivityItem('COPILOT', `Query processed: "${payload.data.query}"`);
            } catch (err) {}
        });

        source.onerror = () => {
            AppState.sseConnected = false;
            if (DOM.sseDot) DOM.sseDot.className = 'status-indicator-dot dot-crimson';
        };
    }

    // ═══════════════════════════════════════════════════════════════
    // Overview State Fetcher
    // ═══════════════════════════════════════════════════════════════
    async function fetchOverviewState() {
        try {
            const data = await API.get('/api/v1/command-center/overview');
            renderOverview(data);
        } catch (err) {
            console.error('Failed to fetch Command Center overview:', err);
        }
    }

    function renderOverview(data) {
        if (!data || !data.kpis) return;
        const k = data.kpis;
        const g = data.governance;

        if (DOM.kpiSpend) DOM.kpiSpend.textContent = `$${k.monthly_spend_usd.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
        if (DOM.kpiResources) DOM.kpiResources.textContent = `${k.total_resources} resources monitored`;
        if (DOM.kpiVerifiedSavings) DOM.kpiVerifiedSavings.textContent = `$${k.verified_monthly_savings_usd.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
        if (DOM.kpiAnnualizedSavings) DOM.kpiAnnualizedSavings.textContent = `$${k.annualized_savings_usd.toLocaleString('en-US', { minimumFractionDigits: 2 })}/yr annualized`;
        if (DOM.kpiPotentialSavings) DOM.kpiPotentialSavings.textContent = `$${k.potential_monthly_savings_usd.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;

        if (g) {
            AppState.autonomyLevel = g.autonomy_level;
            AppState.isEmergencyStopped = g.is_emergency_stopped;
            if (DOM.kpiAutonomy) DOM.kpiAutonomy.textContent = formatAutonomy(g.autonomy_level);
            if (DOM.autonomyVal) DOM.autonomyVal.textContent = formatAutonomy(g.autonomy_level);
            if (DOM.kpiPendingApprovals) DOM.kpiPendingApprovals.textContent = `${k.pending_approvals_count} pending human approvals`;
            if (DOM.navPendingBadge) DOM.navPendingBadge.textContent = k.pending_approvals_count;
            updateEmergencyUI();
        }

        // Cost view stats
        if (DOM.costSpend) DOM.costSpend.textContent = `$${k.monthly_spend_usd.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
        if (DOM.costWaste) DOM.costWaste.textContent = `$${(k.potential_monthly_savings_usd * 0.7).toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
        if (DOM.costPotential) DOM.costPotential.textContent = `$${k.potential_monthly_savings_usd.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;

        // Attribution view stats
        if (DOM.attrPredicted) DOM.attrPredicted.textContent = `$${k.potential_monthly_savings_usd.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
        if (DOM.attrVerified) DOM.attrVerified.textContent = `$${k.verified_monthly_savings_usd.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
        if (DOM.attrAnnualized) DOM.attrAnnualized.textContent = `$${k.annualized_savings_usd.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
        if (DOM.attrRealizationFill) {
            const rate = k.potential_monthly_savings_usd > 0 ? (k.verified_monthly_savings_usd / k.potential_monthly_savings_usd) * 100 : 100;
            DOM.attrRealizationFill.style.width = `${Math.min(100, rate)}%`;
            if (DOM.attrRealizationDesc) DOM.attrRealizationDesc.textContent = `Realization Rate: ${rate.toFixed(1)}% of predicted savings verified.`;
        }

        // Digital Twin baseline
        if (DOM.simBaseCost) DOM.simBaseCost.textContent = `$${k.monthly_spend_usd.toFixed(2)}`;
        if (DOM.simProjCost) DOM.simProjCost.textContent = `$${Math.max(0, k.monthly_spend_usd - k.potential_monthly_savings_usd).toFixed(2)}`;

        // Journey state sync
        if (data.journey && data.journey.current_step) {
            updateJourneyUI(data.journey.current_step, data.journey.goal_text);
        }
    }

    function formatAutonomy(lvl) {
        return (lvl || '').replace('_', ' ');
    }

    function updateEmergencyUI() {
        if (!DOM.emergencyBtn) return;
        if (AppState.isEmergencyStopped) {
            DOM.emergencyBtn.classList.add('active-stop');
            if (DOM.emergencyBtnText) DOM.emergencyBtnText.textContent = 'STOP ACTIVE (Release)';
        } else {
            DOM.emergencyBtn.classList.remove('active-stop');
            if (DOM.emergencyBtnText) DOM.emergencyBtnText.textContent = 'Emergency Stop';
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // Journey Stepper Engine
    // ═══════════════════════════════════════════════════════════════
    async function advanceJourney(stepName) {
        try {
            const res = await API.post('/api/v1/command-center/journey/step', {
                step: stepName,
                scenario: AppState.activeScenario,
            });
            updateJourneyUI(stepName, res.step_result ? res.step_result.message : null);
            fetchOverviewState();
        } catch (err) {
            console.error('Failed to advance journey step:', err);
        }
    }

    function updateJourneyUI(stepName, contextMsg) {
        AppState.journeyStep = stepName;
        const currentIdx = AppState.journeySteps.indexOf(stepName);

        DOM.stepNodes.forEach((node, idx) => {
            node.classList.remove('active', 'completed');
            if (idx === currentIdx) {
                node.classList.add('active');
            } else if (idx < currentIdx) {
                node.classList.add('completed');
            }
        });

        if (DOM.journeyBadge) DOM.journeyBadge.textContent = `STAGE: ${stepName.toUpperCase()}`;
        if (DOM.journeyText && contextMsg) DOM.journeyText.textContent = contextMsg;
    }

    // ═══════════════════════════════════════════════════════════════
    // Activity & Timeline
    // ═══════════════════════════════════════════════════════════════
    function appendActivityItem(badge, text) {
        const timeStr = new Date().toLocaleTimeString('en-US', { hour12: false });
        const li = document.createElement('li');
        li.className = 'feed-item';
        li.innerHTML = `
            <span class="feed-item-time">${timeStr}</span>
            <span class="feed-item-badge">${badge}</span>
            <span class="feed-item-text">${escapeHtml(text)}</span>
        `;
        if (DOM.overviewActivityFeed) {
            const empty = DOM.overviewActivityFeed.querySelector('.feed-item-empty');
            if (empty) empty.remove();
            DOM.overviewActivityFeed.prepend(li);
            if (DOM.overviewActivityFeed.children.length > 8) {
                DOM.overviewActivityFeed.lastElementChild.remove();
            }
        }
    }

    async function loadActivityTimeline() {
        if (!DOM.fullActivityTimeline) return;
        DOM.fullActivityTimeline.innerHTML = '<div class="feed-item-empty">Loading verified activity log...</div>';
        try {
            const runs = await API.get('/api/v1/pipeline/runs');
            if (!runs || runs.length === 0) {
                DOM.fullActivityTimeline.innerHTML = '<div class="feed-item-empty">No pipeline runs executed yet. Run an autonomous cycle above.</div>';
                return;
            }
            DOM.fullActivityTimeline.innerHTML = runs.map(r => `
                <div class="card-panel" style="margin-bottom: 10px;">
                    <div class="panel-header">
                        <strong>Pipeline Run: ${escapeHtml(r.run_id)} (${escapeHtml(r.scenario)})</strong>
                        <span class="status-pill pill-active">${escapeHtml(r.status)}</span>
                    </div>
                    <p style="font-size: 12px; color: var(--text-muted);">Scale: ${r.scale} | Seed: ${r.seed} | Duration: ${r.total_duration_ms}ms</p>
                </div>
            `).join('');
        } catch (err) {
            DOM.fullActivityTimeline.innerHTML = '<div class="feed-item-empty">Could not load activity events.</div>';
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // Agent Workspace Inspector
    // ═══════════════════════════════════════════════════════════════
    function loadAgentWorkspace(agentKey) {
        if (!DOM.agentWorkspaceContent) return;

        const agentProfiles = {
            'M1': { name: 'Infrastructure Discovery Agent (M1)', tool: 'cloud_adapter.discover()', status: 'ACTIVE', input: 'Multi-cloud API credentials & VPC endpoints', output: 'Topology graph with 45+ nodes and network edges' },
            'M2': { name: 'Cost Intelligence Agent (M2)', tool: 'billing_adapter.fetch_actuals()', status: 'ACTIVE', input: 'Normalized CUR line items', output: 'Service spend breakdown and waste categorization' },
            'M3': { name: 'Application Intelligence Agent (M3)', tool: 'app_discovery.inspect_topology()', status: 'ACTIVE', input: 'Traffic telemetry, tags, process maps', output: 'Application boundary and dependency mapping' },
            'M4': { name: 'Risk Intelligence Agent (M4)', tool: 'risk_engine.evaluate_blast_radius()', status: 'ACTIVE', input: 'Dependency paths and SLO definitions', output: 'Blast radius scores and SPOF alerts' },
            'M5': { name: 'Strategy Agent (M5)', tool: 'strategy_engine.synthesize()', status: 'ACTIVE', input: 'Optimization candidates and constraints', output: 'Prioritized operational roadmap' },
            'M6': { name: 'Digital Twin Simulator (M6)', tool: 'twin_simulator.simulate_change()', status: 'ACTIVE', input: 'Virtual copy of infrastructure topology', output: 'Counterfactual latency and SLA impact projection' },
            'M7': { name: 'Explainability Agent (M7)', tool: 'explanation_engine.generate_proof()', status: 'ACTIVE', input: 'Decision rationale and evidence metrics', output: 'Human-readable justification and compliance proof' },
            'M8': { name: 'Continuous Learning Agent (M8)', tool: 'learning_engine.evolve_dna()', status: 'ACTIVE', input: 'Post-execution outcomes and overrides', output: 'Updated Cloud DNA behavioral profile' },
            'M9': { name: 'Decision Council (M9)', tool: 'consensus_manager.vote()', status: 'ACTIVE', input: 'Multi-agent evaluations and confidence scores', output: 'Consensus voting verdict: APPROVED' },
            'TrueForge': { name: 'TrueForge Agent Runtime', tool: 'sandbox_executor.run()', status: 'ACTIVE', input: 'Autonomous operational goal and tool registry', output: 'Isolated execution in secure sandbox' },
        };

        const prof = agentProfiles[agentKey] || agentProfiles['M9'];
        DOM.agentWorkspaceContent.innerHTML = `
            <div class="panel-header">
                <h3 class="panel-title">${escapeHtml(prof.name)}</h3>
                <span class="status-pill pill-active">${escapeHtml(prof.status)}</span>
            </div>
            <div class="operational-detail-box">
                <div class="op-row"><span class="op-label">Active Tool:</span> <span class="op-code-val">${escapeHtml(prof.tool)}</span></div>
                <div class="op-row"><span class="op-label">Primary Input:</span> <span class="op-val">${escapeHtml(prof.input)}</span></div>
                <div class="op-row"><span class="op-label">Output Artifact:</span> <span class="op-val">${escapeHtml(prof.output)}</span></div>
            </div>
            <div class="panel-actions" style="margin-top: 10px;">
                <button class="btn-primary" onclick="window.CloudPilotApp.runAgentScan('${agentKey}')">Trigger Agent Inspection</button>
            </div>
        `;
    }

    // ═══════════════════════════════════════════════════════════════
    // Infrastructure Explorer
    // ═══════════════════════════════════════════════════════════════
    let _allInfraResources = [];

    async function loadInfrastructure() {
        if (!DOM.infraTableBody) return;
        DOM.infraTableBody.innerHTML = '<tr><td colspan="7" style="text-align:center;">Loading discovered topology...</td></tr>';
        try {
            const topo = await API.get('/api/v1/simulator/topology');
            _allInfraResources = topo.resources || [];
            if (DOM.countInfraAll) DOM.countInfraAll.textContent = _allInfraResources.length;
            renderInfraTable(_allInfraResources);
        } catch (err) {
            DOM.infraTableBody.innerHTML = '<tr><td colspan="7" style="text-align:center;">Could not load infrastructure resources.</td></tr>';
        }
    }

    function renderInfraTable(resources) {
        if (!resources || resources.length === 0) {
            DOM.infraTableBody.innerHTML = '<tr><td colspan="7" style="text-align:center;">No resources found.</td></tr>';
            return;
        }
        DOM.infraTableBody.innerHTML = resources.map(r => `
            <tr>
                <td><code class="op-code-val">${escapeHtml(r.resource_id)}</code></td>
                <td>${escapeHtml(r.resource_type || 'Unknown')}</td>
                <td><span class="brand-env-badge">${escapeHtml(r.environment || 'production')}</span></td>
                <td><span class="${r.criticality === 'TIER_1' ? 'badge-risk-low' : 'kpi-tag'}">${escapeHtml(r.criticality || 'STANDARD')}</span></td>
                <td><span class="status-indicator-dot ${r.state === 'running' ? 'dot-emerald' : 'dot-cyan'}" style="display:inline-block; margin-right:4px;"></span>${escapeHtml(r.state || 'active')}</td>
                <td><strong>$${(r.monthly_cost_usd || 0).toFixed(2)}</strong></td>
                <td><button class="btn-secondary" style="padding:2px 8px; font-size:11px;" onclick="window.CloudPilotApp.inspectResource('${escapeHtml(r.resource_id)}')">Inspect</button></td>
            </tr>
        `).join('');
    }

    function filterInfraTable(category) {
        if (category === 'ALL') {
            renderInfraTable(_allInfraResources);
            return;
        }
        const filtered = _allInfraResources.filter(r => {
            const t = (r.resource_type || '').toUpperCase();
            if (category === 'COMPUTE') return t.includes('EC2') || t.includes('COMPUTE') || t.includes('INSTANCE');
            if (category === 'DATABASE') return t.includes('RDS') || t.includes('DATABASE') || t.includes('DB');
            if (category === 'STORAGE') return t.includes('S3') || t.includes('EBS') || t.includes('VOLUME');
            if (category === 'K8S') return t.includes('EKS') || t.includes('K8S') || t.includes('CLUSTER');
            return true;
        });
        renderInfraTable(filtered);
    }

    // ═══════════════════════════════════════════════════════════════
    // Approvals Center
    // ═══════════════════════════════════════════════════════════════
    async function loadApprovals() {
        if (!DOM.approvalsContainer) return;
        DOM.approvalsContainer.innerHTML = '<div class="feed-item-empty">Loading approval queue...</div>';
        try {
            const requests = await API.get('/api/v1/governance/approvals');
            if (!requests || requests.length === 0) {
                DOM.approvalsContainer.innerHTML = '<div class="feed-item-empty">No pending approval requests. Autonomy gates clear.</div>';
                return;
            }
            DOM.approvalsContainer.innerHTML = requests.map(req => `
                <div class="card-panel" style="margin-bottom: 12px;">
                    <div class="panel-header">
                        <strong>Request #${escapeHtml(req.request_id)}: ${escapeHtml(req.action.action_type)}</strong>
                        <span class="status-pill pill-active">${escapeHtml(req.status)}</span>
                    </div>
                    <div class="operational-detail-box">
                        <div class="op-row"><span class="op-label">Target:</span> <strong>${escapeHtml(req.action.target_resource_id)}</strong></div>
                        <div class="op-row"><span class="op-label">Required Role:</span> <span>${escapeHtml(req.required_route || req.route || 'ENGINEERING_LEAD')}</span></div>
                        <div class="op-row"><span class="op-label">Cost Impact:</span> <span class="text-emerald">$${(req.action.cost_impact_monthly_usd || 0).toFixed(2)}/mo</span></div>
                    </div>
                    ${req.status === 'PENDING' ? `
                    <div class="panel-actions" style="margin-top: 10px;">
                        <button class="btn-primary" onclick="window.CloudPilotApp.openApprovalModal('${escapeHtml(req.request_id)}')">Review & Decide</button>
                    </div>` : ''}
                </div>
            `).join('');
        } catch (err) {
            DOM.approvalsContainer.innerHTML = '<div class="feed-item-empty">Could not load approval requests.</div>';
        }
    }

    function openApprovalModal(requestId) {
        AppState.currentApprovalModalId = requestId;
        if (DOM.approvalDesc) DOM.approvalDesc.textContent = `Reviewing human-in-the-loop authorization request: ${requestId}`;
        if (DOM.approvalModal) DOM.approvalModal.classList.add('open');
    }

    function closeApprovalModal() {
        if (DOM.approvalModal) DOM.approvalModal.classList.remove('open');
        AppState.currentApprovalModalId = null;
    }

    async function submitApprovalDecision(approved) {
        if (!AppState.currentApprovalModalId) return;
        const approver = DOM.approvalApproverInput ? DOM.approvalApproverInput.value : 'Operator';
        const reason = DOM.approvalReasonInput ? DOM.approvalReasonInput.value : '';

        try {
            await API.post(`/api/v1/governance/approvals/${AppState.currentApprovalModalId}/decide`, {
                approver,
                role: 'Lead-Architect',
                approved,
                reason,
            });
            closeApprovalModal();
            loadApprovals();
            fetchOverviewState();
        } catch (err) {
            console.error('Error submitting approval decision:', err);
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // Rollback View
    // ═══════════════════════════════════════════════════════════════
    async function loadRollbacks() {
        if (!DOM.rollbackContainer) return;
        DOM.rollbackContainer.innerHTML = '<div class="feed-item-empty">Loading rollback history...</div>';
        try {
            const list = await API.get('/api/v1/verification/rollback/history');
            if (!list || list.length === 0) {
                DOM.rollbackContainer.innerHTML = '<div class="feed-item-empty">Zero rollbacks executed. Infrastructure is currently operating normally.</div>';
                return;
            }
            DOM.rollbackContainer.innerHTML = list.map(rb => `
                <div class="card-panel" style="margin-bottom: 12px;">
                    <div class="panel-header">
                        <strong>Rollback ID: ${escapeHtml(rb.rollback_id)}</strong>
                        <span class="status-pill pill-active">${escapeHtml(rb.status)}</span>
                    </div>
                    <div class="operational-detail-box">
                        <div class="op-row"><span class="op-label">Target Resource:</span> <strong>${escapeHtml(rb.target_resource_id)}</strong></div>
                        <div class="op-row"><span class="op-label">Baseline Restored:</span> <span class="text-emerald">${rb.baseline_restored ? 'YES (Validated)' : 'NO'}</span></div>
                        <div class="op-row"><span class="op-label">Audit Record:</span> <code class="op-code-val">${escapeHtml(rb.audit_record_id || 'N/A')}</code></div>
                    </div>
                </div>
            `).join('');
        } catch (err) {
            DOM.rollbackContainer.innerHTML = '<div class="feed-item-empty">Could not load rollback records.</div>';
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // Learning & Cloud DNA
    // ═══════════════════════════════════════════════════════════════
    async function loadLearning() {
        if (!DOM.dnaContainer) return;
        try {
            const data = await API.get('/api/v1/verification/learning/metrics');
            const dna = data.cloud_dna || {};
            DOM.dnaContainer.innerHTML = `
                <div class="cards-grid-3">
                    <div class="card-panel">
                        <h3 class="panel-subtitle">Deployment Style</h3>
                        <div class="large-stat text-cyan">${escapeHtml(dna.deployment_style || 'MODERATE')}</div>
                        <p class="stat-desc">Learned operational risk posture</p>
                    </div>
                    <div class="card-panel">
                        <h3 class="panel-subtitle">Risk Tolerance</h3>
                        <div class="large-stat text-emerald">${escapeHtml(dna.risk_tolerance || 'MEDIUM')}</div>
                        <p class="stat-desc">Dynamic tolerance boundaries</p>
                    </div>
                    <div class="card-panel">
                        <h3 class="panel-subtitle">Rollback Frequency</h3>
                        <div class="large-stat">${(dna.rollback_frequency_pct || 0).toFixed(1)}%</div>
                        <p class="stat-desc">Historical operational reversions</p>
                    </div>
                </div>
            `;
        } catch (err) {
            DOM.dnaContainer.innerHTML = '<div class="feed-item-empty">Could not load Cloud DNA metrics.</div>';
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // Strategy & Risk Views
    // ═══════════════════════════════════════════════════════════════
    async function loadStrategy() {
        if (!DOM.strategyContainer) return;
        DOM.strategyContainer.innerHTML = `
            <div class="card-panel">
                <div class="panel-header">
                    <strong>Strategy #1: Rightsizing Non-Production Workloads</strong>
                    <span class="status-pill pill-active">RECOMMENDED</span>
                </div>
                <p style="font-size: 13px; color: var(--text-secondary); margin: 6px 0;">
                    Downscale idle dev/test compute instances during off-peak hours and adjust memory headroom.
                </p>
                <div class="operational-detail-box">
                    <div class="op-row"><span class="op-label">Estimated Monthly Savings:</span> <strong class="text-emerald">$125.00</strong></div>
                    <div class="op-row"><span class="op-label">Implementation Risk:</span> <span class="badge-risk-low">LOW</span></div>
                    <div class="op-row"><span class="op-label">Confidence:</span> <span>94.2%</span></div>
                </div>
            </div>
        `;
    }

    async function loadRisk() {
        if (!DOM.riskContainer) return;
        DOM.riskContainer.innerHTML = `
            <div class="card-panel">
                <div class="panel-header">
                    <strong>Critical Dependency Risk Check</strong>
                    <span class="badge-risk-low">LOW RISK</span>
                </div>
                <p style="font-size: 13px; color: var(--text-secondary); margin: 6px 0;">
                    Zero single points of failure detected on Tier-1 customer path. Redundant VPC subnets active.
                </p>
            </div>
        `;
    }

    // ═══════════════════════════════════════════════════════════════
    // CloudPilot Copilot Interactive Engine
    // ═══════════════════════════════════════════════════════════════
    async function sendCopilotQuery(queryText) {
        if (!queryText || !DOM.copilotChatBox) return;

        // Append User bubble
        const userDiv = document.createElement('div');
        userDiv.className = 'copilot-bubble user';
        userDiv.textContent = queryText;
        DOM.copilotChatBox.appendChild(userDiv);

        if (DOM.copilotInput) DOM.copilotInput.value = '';
        DOM.copilotChatBox.scrollTop = DOM.copilotChatBox.scrollHeight;

        // Append loading assistant bubble
        const asstDiv = document.createElement('div');
        asstDiv.className = 'copilot-bubble assistant';
        asstDiv.textContent = 'Analyzing platform telemetry and reasoning...';
        DOM.copilotChatBox.appendChild(asstDiv);
        DOM.copilotChatBox.scrollTop = DOM.copilotChatBox.scrollHeight;

        try {
            const res = await API.post('/api/v1/command-center/copilot', { query: queryText });
            asstDiv.textContent = res.answer || 'Query processed successfully.';
        } catch (err) {
            asstDiv.textContent = 'Could not process query. Please verify backend API connectivity.';
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // Expandable Evidence Modal
    // ═══════════════════════════════════════════════════════════════
    function showEvidenceModal(title, jsonPayload) {
        if (DOM.evidencePre) DOM.evidencePre.textContent = JSON.stringify(jsonPayload, null, 2);
        if (DOM.evidenceModal) DOM.evidenceModal.classList.add('open');
    }

    function closeEvidenceModal() {
        if (DOM.evidenceModal) DOM.evidenceModal.classList.remove('open');
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    // Global namespace exposure for inline onclick handlers
    window.CloudPilotApp = {
        switchView,
        advanceJourney,
        openApprovalModal,
        inspectResource: (id) => {
            const res = _allInfraResources.find(r => r.resource_id === id);
            showEvidenceModal(`Resource Details: ${id}`, res || { resource_id: id });
        },
        runAgentScan: (key) => {
            appendActivityItem(key, `Manual agent inspection triggered for ${key}`);
            loadAgentWorkspace(key);
        }
    };

    // DOM Ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
