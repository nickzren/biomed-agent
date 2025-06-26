import streamlit as st
import asyncio
import json
import sys
from pathlib import Path
import nest_asyncio
from datetime import datetime
import time
import os

# Allow nested event loops in Streamlit
nest_asyncio.apply()

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from core import BiomedAgent
from core.agent import MCP_SERVERS

# Page config
st.set_page_config(
    page_title="Biomedical Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- STYLING AND ICONS ---
st.markdown('<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">', unsafe_allow_html=True)
st.markdown("""
<style>
    /* Reset and base styles */
    .main {
        background-color: #fafbfc;
        padding: 1rem 2rem;
    }
    
    hr {
        margin-top: 0.5rem !important;
        margin-bottom: 1rem !important;
    }
    
    /* Clean typography */
    h1 {
        color: #24292f;
        font-weight: 600;
        font-size: 2rem;
        margin-bottom: 0.5rem;
    }
    
    h2 {
        color: #24292f;
        font-weight: 600;
        font-size: 1.5rem;
        margin-bottom: 1rem;
    }
    
    h3 {
        color: #24292f;
        font-weight: 500;
        font-size: 1.25rem;
        margin-bottom: 0.75rem;
    }
    
    /* Sidebar - clean white */
    section[data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid #e1e4e8;
    }
    
    /* Buttons - subtle blue */
    .stButton > button {
        background-color: #ffffff;
        color: #0969da;
        border: 1px solid #d1d9e0;
        padding: 0.5rem 1rem;
        font-weight: 500;
        border-radius: 6px;
        transition: all 0.2s ease;
    }
    
    .stButton > button:hover {
        background-color: #f3f4f6;
        border-color: #0969da;
    }
    
    /* Primary buttons */
    .stButton > button[kind="primary"] {
        background-color: #0969da;
        color: white;
        border: none;
    }
    
    .stButton > button[kind="primary"]:hover {
        background-color: #0860ca;
    }
    
    /* Chat messages - clean cards */
    .stChatMessage {
        background-color: #ffffff;
        border: 1px solid #e1e4e8;
        border-radius: 6px;
        padding: 1rem;
        margin-bottom: 0.75rem;
    }
    
    /* Input fields */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea {
        background-color: #ffffff;
        border: 1px solid #d1d9e0;
        border-radius: 6px;
        color: #24292f;
    }
    
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus {
        border-color: #0969da;
        box-shadow: 0 0 0 3px rgba(9, 105, 218, 0.1);
    }
    
    /* Tabs - minimal style */
    .stTabs [data-baseweb="tab-list"] {
        background-color: transparent;
        border-bottom: 1px solid #e1e4e8;
        gap: 0;
    }
    
    .stTabs [data-baseweb="tab"] {
        background-color: transparent;
        border: none;
        color: #57606a;
        padding: 0.75rem 1.5rem;
        font-weight: 500;
        border-bottom: 2px solid transparent;
        border-radius: 0;
    }
    
    .stTabs [data-baseweb="tab"]:hover {
        color: #24292f;
        border-bottom-color: #d1d9e0;
    }
    
    .stTabs [aria-selected="true"] {
        color: #0969da;
        border-bottom-color: #0969da;
    }
    
    /* Metrics - clean style */
    [data-testid="metric-container"] {
        background-color: #ffffff;
        border: 1px solid #e1e4e8;
        padding: 1rem;
        border-radius: 6px;
        box-shadow: none;
    }
    
    [data-testid="metric-container"] [data-testid="metric-label"] {
        color: #57606a;
        font-size: 0.875rem;
        font-weight: 400;
    }
    
    [data-testid="metric-container"] [data-testid="metric-value"] {
        color: #24292f;
        font-size: 1.5rem;
        font-weight: 600;
    }
    
    /* Expanders - minimal */
    .streamlit-expanderHeader {
        background-color: #f6f8fa;
        border: 1px solid #e1e4e8;
        border-radius: 6px;
        font-weight: 500;
        color: #24292f;
    }
    
    .streamlit-expanderHeader:hover {
        background-color: #f3f4f6;
    }
    
    /* Info/Success/Error boxes - subtle */
    .stAlert {
        background-color: #ffffff;
        border: 1px solid;
        border-radius: 6px;
        padding: 0.75rem 1rem;
    }
    
    div[data-baseweb="notification"] {
        background-color: #ffffff;
        border-radius: 6px;
    }
    
    /* Code blocks - GitHub style */
    .stCodeBlock {
        background-color: #f6f8fa;
        border: 1px solid #e1e4e8;
        border-radius: 6px;
    }
    
    code {
        background-color: #f6f8fa;
        padding: 0.125rem 0.25rem;
        border-radius: 3px;
        font-size: 0.875rem;
        color: #0969da;
    }
    
    /* Remove excessive shadows */
    .element-container {
        box-shadow: none !important;
    }
    
    /* Clean cards */
    .card {
        background-color: #ffffff;
        border: 1px solid #e1e4e8;
        border-radius: 6px;
        padding: 1.5rem;
        margin-bottom: 1rem;
    }
    
    /* Welcome page */
    .welcome-container {
        max-width: 800px;
        margin: 0 auto;
        text-align: center;
        padding: 2rem;
    }
        
    .welcome-title {
        font-size: 2.5rem;
        font-weight: 600;
        color: #24292f;
        margin-bottom: 1rem;
    }
    
    .welcome-subtitle {
        font-size: 1.25rem;
        color: #57606a;
        margin-bottom: 2rem;
    }
    
    .feature-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
        gap: 1.5rem;
        margin-bottom: 2rem;
    }
    
    .feature-card {
        background: #ffffff;
        border: 1px solid #e1e4e8;
        border-radius: 8px;
        padding: 1.5rem;
        text-align: left;
    }
                
    .feature-title {
        font-weight: 600;
        color: #24292f;
        margin-bottom: 0.5rem;
    }
    
    .feature-desc {
        color: #57606a;
        font-size: 0.9rem;
    }
    
    /* Status indicator */
    .status-indicator {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.375rem 0.75rem;
        border-radius: 20px;
        font-size: 0.875rem;
        font-weight: 500;
        margin-bottom: 1rem;
    }
    
    .status-connected {
        background-color: #dafbe1;
        color: #1a7f37;
    }
    
    .status-disconnected {
        background-color: #ffedd5;
        color: #c2410c;
    }
    
    /* Data source item */
    .data-source-item {
        padding: 0.5rem 0.75rem;
        border-radius: 6px;
        margin-bottom: 0.25rem;
        background: #f6f8fa;
        border: 1px solid transparent;
        transition: all 0.2s ease;
    }
    
    .data-source-item:hover {
        background: #ffffff;
        border-color: #e1e4e8;
    }
    
    .data-source-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 0.25rem;
    }
    
    .data-source-title {
        font-weight: 600;
        color: #24292f;
        font-size: 0.9rem;
    }
    
    .data-source-status {
        font-size: 0.75rem;
        padding: 0.125rem 0.5rem;
        border-radius: 10px;
    }
    
    .status-available {
        background: #dafbe1;
        color: #1a7f37;
    }
    
    .status-unavailable {
        background: #ffebe9;
        color: #cf222e;
    }
    
    .data-source-desc {
        font-size: 0.8rem;
        color: #57606a;
        line-height: 1.4;
    }
</style>
""", unsafe_allow_html=True)

# Helper function to run async code
def run_async(coro):
    """Run async function in Streamlit context"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

# Initialize session state
if 'agent' not in st.session_state:
    st.session_state.agent = None
    st.session_state.connected = False
    st.session_state.messages = []
    st.session_state.query_history = []

# --- SIDEBAR ---
with st.sidebar:
    st.markdown("### <i class='bi bi-hdd-stack'></i> MCP Server Connections", unsafe_allow_html=True)
    st.caption("Manage connections to data sources.")
    st.markdown("---")

    st.markdown("#### Select Data Sources")
    selected_servers = []
    
    for name, config in MCP_SERVERS.items():
        env_var = f"{name.upper()}_MCP_PATH"
        path = Path(os.getenv(env_var, f"../{name}-mcp"))
        is_available = path.exists()
        
        st.checkbox(
            name.upper(), 
            value=is_available, 
            key=f"server_{name}", 
            disabled=not is_available or st.session_state.connected
        )
        if st.session_state.get(f"server_{name}") and is_available:
            selected_servers.append(name)
        
        status_class = "status-available" if is_available else "status-unavailable"
        status_text = "Available" if is_available else "Not Found"
        
        st.markdown(f"""
        <div class="data-source-item">
            <div class="data-source-header">
                <span class="data-source-desc">{config["description"]}</span>
                <span class="data-source-status {status_class}">{status_text}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    st.markdown("#### Connection Control")
    if st.session_state.connected:
        st.markdown('<div class="status-indicator status-connected">● Connected</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="status-indicator status-disconnected">● Disconnected</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        connect_btn = st.button(
            "Connect",
            type="primary",
            use_container_width=True,
            disabled=st.session_state.connected or not selected_servers
        )
    
    with col2:
        disconnect_btn = st.button(
            "Disconnect",
            use_container_width=True,
            disabled=not st.session_state.connected
        )
    
    if connect_btn:
        with st.spinner("Connecting to servers..."):
            try:
                agent = BiomedAgent(selected_servers)
                run_async(agent.connect())
                st.session_state.agent = agent
                st.session_state.connected = True
                st.rerun()
            except Exception as e:
                st.error(f"Connection failed: {str(e)}")
    
    if disconnect_btn:
        agent_to_disconnect = st.session_state.get("agent")
        
        st.session_state.connected = False
        st.session_state.agent = None
        st.session_state.messages = []
        st.session_state.query_history = []
        
        if agent_to_disconnect:
            try:
                with st.spinner("Disconnecting..."):
                    run_async(agent_to_disconnect.disconnect())
            except Exception as e:
                print(f"Error during disconnect: {e}")
                st.warning(f"Could not cleanly disconnect from servers: {e}")
        
        st.rerun()

# --- MAIN CONTENT ---
if st.session_state.connected:
    st.markdown("<h1><i class='bi bi-robot'></i> Biomedical Agent</h1>", unsafe_allow_html=True)
    st.markdown("Query multiple biomedical databases with an AI-powered research assistant")
    
    tab1, tab2, tab3, tab4 = st.tabs([
        "💬 Chat",
        "🔍 Direct Query",
        "🛠️ Tools Explorer",
        "📊 History"
    ])
    
    with tab1:
        if not st.session_state.messages:
            st.markdown("#### Example Questions")
            
            examples = [
                "What drugs target BRAF and are used for melanoma?",
                "Find the phenotypes associated with Parkinson's disease",
                "What are the safety liabilities of imatinib?",
                "Which genes are associated with type 2 diabetes?"
            ]
            
            cols = st.columns(2)
            for idx, example in enumerate(examples):
                if cols[idx % 2].button(example, key=f"ex_{idx}", use_container_width=True):
                    st.session_state.messages.append({"role": "user", "content": example})
                    st.rerun()
            st.markdown("---")
        
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])
                if "reasoning_steps" in msg:
                    with st.expander("View Reasoning"):
                        for i, step in enumerate(msg["reasoning_steps"]):
                            if "thought" in step:
                                st.markdown(f"**Step {i+1}: Thought**")
                                st.info(step["thought"])
                            if "action" in step and step.get("action"):
                                st.markdown(f"**Step {i+1}: Action**")
                                st.code(f"Tool: {step['action']['tool']}\nArguments: {json.dumps(step['action']['arguments'], indent=2)}", language="json")
                            if "observation" in step:
                                st.markdown(f"**Step {i+1}: Observation**")
                                st.json(step["observation"])
        
        if prompt := st.chat_input("Ask a question..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.write(prompt)

            with st.chat_message("assistant"):
                with st.spinner("Researching..."):
                    try:
                        response = run_async(st.session_state.agent.reason_and_act(prompt))
                        answer = response["answer"]
                        st.write(answer)
                        
                        msg_data = {
                            "role": "assistant",
                            "content": answer,
                            "reasoning_steps": response["steps"]
                        }
                        st.session_state.messages.append(msg_data)
                        st.session_state.query_history.append({
                            "query": prompt, "answer": answer, 
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
        
        if st.session_state.messages:
            if st.button("Clear Chat", key="clear_chat"):
                st.session_state.messages = []
                st.rerun()
    
    with tab2:
        st.markdown("#### Execute a Direct Query")
        query = st.text_area("Enter your research question:", height=100)
        
        col1, col2, _ = st.columns([1,1,2])
        max_steps = col1.number_input("Max Steps", 1, 20, 10)
        show_details = col2.checkbox("Show Details", value=True)
        
        if st.button("Execute Query", type="primary", disabled=not query):
            with st.spinner("Processing..."):
                try:
                    start_time = time.time()
                    response = run_async(st.session_state.agent.reason_and_act(query, max_steps))
                    elapsed = time.time() - start_time
                    
                    st.success(f"Completed in {elapsed:.2f}s")
                    st.markdown("##### Answer")
                    st.info(response["answer"])
                    
                    if show_details and "steps" in response:
                        st.markdown("##### Reasoning Steps")
                        for i, step in enumerate(response["steps"]):
                            expander_title = "Final Answer"
                            if "thought" in step:
                                expander_title = step["thought"]
                            elif "action" in step and step.get("action"):
                                expander_title = f"Tool Call: {step['action']['tool']}"
                            elif "observation" in step:
                                 expander_title = "Observation"
                            
                            with st.expander(f"Step {i+1}: {expander_title[:80]}"):
                                st.json(step)

                    st.session_state.query_history.append({
                        "query": query, "answer": response["answer"], 
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                        "time": elapsed
                    })
                except Exception as e:
                    st.error(f"Error: {str(e)}")

    with tab3:
        st.markdown("#### Tools Explorer")
        tools = st.session_state.agent.list_all_tools()
        total_tools = sum(len(t) for t in tools.values())
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Tools", total_tools)
        c2.metric("Active Servers", len(tools))
        c3.metric("Status", "Ready")
        st.markdown("---")
        
        search_term = st.text_input("Search tools by name or description")
        
        for server, server_tools in sorted(tools.items()):
            if search_term:
                server_tools = [t for t in server_tools if search_term.lower() in t['id'].lower() or search_term.lower() in t['description'].lower()]

            if not server_tools:
                continue

            with st.expander(f"{server.upper()} ({len(server_tools)} tools)"):
                for tool in sorted(server_tools, key=lambda x: x['id']):
                    st.markdown(f"**{tool['id']}**")
                    st.caption(tool['description'])
                    st.divider()

    with tab4:
        st.markdown("#### Query History")
        if st.session_state.query_history:
            c1, c2, _ = st.columns(3)
            c1.metric("Total Queries", len(st.session_state.query_history))
            times = [q.get('time', 0) for q in st.session_state.query_history if 'time' in q]
            if times:
                c2.metric("Avg. Time", f"{sum(times)/len(times):.2f}s")

            for item in reversed(st.session_state.query_history):
                with st.expander(f"{item['timestamp']} - {item['query'][:70]}"):
                    st.write(f"**Query:** {item['query']}")
                    st.info(f"**Answer:** {item['answer']}")
                    if 'time' in item:
                        st.caption(f"Time taken: {item['time']:.2f}s")
        else:
            st.info("No queries have been made in this session.")

else:
    # --- WELCOME PAGE ---
    st.html("""
    <div class="welcome-container">
        <h1 class="welcome-title"><i class='bi bi-robot'></i> Biomedical Agent</h1>
        <p class="welcome-subtitle">AI-powered research assistant for biomedical databases</p>
        
        <p style="color: #57606a; font-size: 1.1rem;">
            Select data sources and connect using the sidebar to begin →
        </p>
    </div>
    """)