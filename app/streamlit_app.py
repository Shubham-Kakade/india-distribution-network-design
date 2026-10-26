"""What-if agent front end (spec §10): chat on the left, the current network on the right.

Run from the project root: streamlit run app/streamlit_app.py
Live mode needs LLM_BASE_URL, LLM_API_KEY and LLM_MODEL (D-039); without them the app answers
from the offline library. The sidebar shows the mode, provider and model, never the key.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # `streamlit run` from the root

from src import viz
from src.agent import Agent, LLMConfig, OfflineAgent
from src.agent_offline import LIBRARY_PATH
from src.agent_tools import ToolBox
from src.config import load_params
from src.data_prep import load_network_data
from src.model import COMPONENTS

DISCLAIMER = (
    "Independent portfolio project, not affiliated with Cushman & Wakefield; hypothetical client."
)
MAP_HEIGHT_PX = 470


@st.cache_resource
def load_toolbox() -> ToolBox:
    """Params, network data and every recorded or library scenario, loaded once per server."""
    toolbox = ToolBox(load_params(), load_network_data())
    library = OfflineAgent.from_file().library
    toolbox.records.update(library["records"])  # agent-made networks the library answers with
    return toolbox


def new_agent(toolbox: ToolBox) -> Agent:
    config = LLMConfig.from_env()
    return Agent(config, toolbox if config.live else None, OfflineAgent.from_file())


def network_panel(toolbox: ToolBox, scenario_id: str) -> None:
    """Map of the scenario's network and its cost by component against the recommended one."""
    record = toolbox.record(scenario_id)
    params = toolbox.params
    if "cost_cr" not in record:
        st.info(f"{scenario_id}: no feasible network to draw.")
        return
    solution = SimpleNamespace(
        open_dcs=tuple(record["open_dcs"]), assignment=pd.Series(record["assignment"])
    )
    radius_km = params["service"]["next_day_radius_km"]["value"]
    ring_gc_km = radius_km / params["distance"]["circuity_factor"]["value"]
    title = (
        f"{scenario_id}: {len(record['open_dcs'])} DCs, INR {record['cost_cr']['total']:.1f} Cr/yr,"
        f" {record['service']['next_day_share_frac']:.1%} next-day"
    )
    fmap = viz.plot_network_map(
        toolbox.data_for(record["open_dcs"]), solution, radius_km, ring_gc_km, title, DISCLAIMER
    )
    components.html(fmap.get_root().render(), height=MAP_HEIGHT_PX)
    rec = toolbox.recommended_record
    fig = viz.plot_cost_comparison(
        {c: record["cost_cr"][c] for c in COMPONENTS},
        {c: rec["cost_cr"][c] for c in COMPONENTS},
        scenario_id,
        toolbox.recommended_id,
    )
    st.pyplot(fig)


def main() -> None:
    st.set_page_config(page_title="India DC network: what-if agent", layout="wide")
    toolbox = load_toolbox()
    if "agent" not in st.session_state:
        st.session_state.agent = new_agent(toolbox)
        st.session_state.turns = []
        st.session_state.scenario_id = toolbox.recommended_id
    agent: Agent = st.session_state.agent

    with st.sidebar:
        st.header("Agent")
        config = agent.config
        st.write(f"**Mode:** {agent.mode}")
        st.write(f"**Provider:** {config.provider if agent.mode == 'live' else 'offline library'}")
        st.write(f"**Model:** {config.model if agent.mode == 'live' else 'none (no network)'}")
        st.caption(f"Offline library: {LIBRARY_PATH.name}, 20 pre-computed questions.")
        st.subheader("Try")
        for entry in agent.offline.library["entries"][:8]:
            st.caption(entry["example"])

    st.title("India distribution network: what-if agent")
    chat, network = st.columns([1, 1])
    question = st.chat_input("Ask a what-if question, e.g. What if Hosur shuts for a month?")
    if question:
        with st.spinner("Running the model..."):
            reply = agent.ask(question)
        st.session_state.turns.append((question, reply))
        for sid in reply.scenario_ids:  # show the first cited scenario that is a network
            try:
                toolbox.record(sid)
            except ValueError:  # a table such as S9_tornado
                continue
            st.session_state.scenario_id = sid
            break

    with chat:
        for asked, reply in st.session_state.turns:
            st.chat_message("user").write(asked)
            with st.chat_message("assistant"):
                if reply.notice:
                    st.warning(reply.notice)
                st.markdown(reply.text)
                tools = ", ".join(name for name, _ in reply.tool_calls) or "none"
                st.caption(f"{reply.mode} · tools: {tools} · grounding: {reply.grounding}")
    with network:
        st.subheader(st.session_state.scenario_id)
        network_panel(toolbox, st.session_state.scenario_id)

    st.divider()
    st.caption(DISCLAIMER)


main()
