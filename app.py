"""Repo Auditor - Windows-Native Streamlit App.

Packer with AST one-hop import resolution, char cap, and 3-pass Agnes AI Auditor.
"""

from pathlib import Path
import json
import streamlit as st

from src.audit import run_three_pass_audit
from src.pack import PackResult, pack_repository, save_pack_cache
from src.providers import get_available_providers
from src.safety import validate_repo_path

st.set_page_config(
    page_title="Repo Auditor",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize Session State
if "selected_repo_path" not in st.session_state:
    st.session_state.selected_repo_path = ""
if "user_ref" not in st.session_state:
    st.session_state.user_ref = ""
if "non_git_glob" not in st.session_state:
    st.session_state.non_git_glob = "**/*.py"
if "file_cap" not in st.session_state:
    st.session_state.file_cap = 50
if "char_cap" not in st.session_state:
    st.session_state.char_cap = 120_000
if "pack_result" not in st.session_state:
    st.session_state.pack_result = None
if "audit_result" not in st.session_state:
    st.session_state.audit_result = None
if "active_nav" not in st.session_state:
    st.session_state.active_nav = "Select repo"


def set_page(page_name: str):
    st.session_state.active_nav = page_name
    st.rerun()


# --- Sidebar Navigation & Model Provider ---
st.sidebar.title("🛡️ Repo Auditor")
st.sidebar.caption("Surgical Codebase Auditing & Packing")

PAGES = ["Select repo", "Pack", "Audit", "Findings"]
page_options = PAGES
nav_choice = st.sidebar.radio(
    "Navigation",
    options=page_options,
    index=page_options.index(st.session_state.active_nav) if st.session_state.active_nav in page_options else 0,
)

if nav_choice != st.session_state.active_nav:
    st.session_state.active_nav = nav_choice

st.sidebar.divider()
st.sidebar.subheader("LLM Provider")

available_providers = get_available_providers()
provider_names = list(available_providers.keys())

if provider_names:
    selected_provider_name = st.sidebar.selectbox(
        "Provider",
        options=provider_names,
        index=0,
    )
    current_provider = available_providers[selected_provider_name]
    selected_model = st.sidebar.selectbox(
        "Model",
        options=current_provider.models,
        index=0,
    )
    if current_provider.has_api_key:
        st.sidebar.success(f"✓ {current_provider.api_key_env_var} active")
    else:
        st.sidebar.warning(f"⚠️ {current_provider.api_key_env_var} missing")
else:
    st.sidebar.error("No configured providers found.")

if st.session_state.pack_result:
    st.sidebar.divider()
    st.sidebar.subheader("Active Workspace")
    res: PackResult = st.session_state.pack_result
    st.sidebar.text(f"Target: {res.repo_path.name}")
    st.sidebar.text(f"Mode: {'Git (' + res.ref_or_glob + ')' if res.is_git else 'Glob (' + res.ref_or_glob + ')'}")
    st.sidebar.text(f"Files: {res.total_files} ({res.total_chars:,} chars)")


# --- Page 1: Select repo ---
if st.session_state.active_nav == "Select repo":
    st.title("📁 Select Repository / Directory")
    st.markdown("Enter local path to a Git repository or project folder. Refuses to scan without an entered path or if set to a drive root (`D:\\`, `C:\\`).")

    repo_input = st.text_input(
        "Local Repository or Folder Path",
        value=st.session_state.selected_repo_path,
        placeholder="e.g. D:\\AI\\Github\\repo-auditor",
        help="Target folder. If .git is present, git diff mode is used; otherwise glob mode is used.",
    )

    col1, col2 = st.columns(2)
    with col1:
        st.session_state.char_cap = st.slider(
            "Character Budget Slider",
            min_value=10_000,
            max_value=500_000,
            value=st.session_state.char_cap,
            step=10_000,
            help="Ceiling for cumulative packed characters (default 120K, well under 512K).",
        )

    with col2:
        candidate_path = Path(repo_input.strip()).resolve() if repo_input.strip() else None
        is_git_target = bool(candidate_path and candidate_path.exists() and (candidate_path / ".git").exists())

        if is_git_target:
            st.session_state.user_ref = st.text_input(
                "Git Compare Ref (Optional)",
                value=st.session_state.user_ref,
                placeholder="e.g. origin/HEAD or main or HEAD~1",
                help="Defaults to origin/HEAD or latest commit diff if empty.",
            )
        else:
            st.session_state.non_git_glob = st.text_input(
                "Non-Git File Glob Pattern",
                value=st.session_state.non_git_glob,
                placeholder="e.g. **/*.py or src/**/*.py",
                help="File glob to match when folder is not a git repository.",
            )
            st.session_state.file_cap = st.number_input(
                "File Cap",
                min_value=1,
                max_value=200,
                value=st.session_state.file_cap,
            )

    if st.button("Inspect Target", type="primary"):
        if not repo_input.strip():
            st.error("Refusing to scan: please enter a repository path first.")
        else:
            target = Path(repo_input.strip()).resolve()
            if not target.exists() or not target.is_dir():
                st.error(f"Path does not exist or is not a directory: {target}")
            elif target == Path(target.anchor) or len(target.parts) <= 1:
                st.error(f"Refusing to scan drive root ({target}). Please specify a subfolder.")
            else:
                st.session_state.selected_repo_path = str(target)
                git_present = (target / ".git").exists()
                mode_str = "Git Repository" if git_present else "Non-Git Directory"
                st.success(f"Validated {mode_str}: `{target}`")

    if st.session_state.selected_repo_path:
        p = Path(st.session_state.selected_repo_path)
        if p.exists() and p.is_dir():
            st.info(f"Target selected: **{p}** ({'Git' if (p / '.git').exists() else 'Non-Git'})")
            if st.button("Proceed to Pack ➡️"):
                set_page("Pack")


# --- Page 2: Pack ---
elif st.session_state.active_nav == "Pack":
    st.title("📦 Repository Packer")

    if not st.session_state.selected_repo_path:
        st.warning("No target selected. Return to 'Select repo' and type a path first.")
        if st.button("⬅️ Go to Select repo"):
            set_page("Select repo")
    else:
        st.markdown(f"Target: `{st.session_state.selected_repo_path}`")
        col_act1, col_act2 = st.columns([1, 4])
        with col_act1:
            pack_button = st.button("Gather & Pack Files", type="primary")

        if pack_button:
            with st.spinner("Packing repository files & resolving AST dependencies..."):
                ok, msg, res = pack_repository(
                    repo_path_str=st.session_state.selected_repo_path,
                    user_ref=st.session_state.user_ref,
                    non_git_glob=st.session_state.non_git_glob,
                    file_cap=st.session_state.file_cap,
                    char_cap=st.session_state.char_cap,
                    auto_cache=True,
                )
                if ok and res:
                    st.session_state.pack_result = res
                    st.success(f"{msg} Saved to `data/cache/last_pack.json`.")
                else:
                    st.error(f"Packaging failed: {msg}")

        if st.session_state.pack_result:
            res: PackResult = st.session_state.pack_result

            # Metrics
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Packed Files", res.total_files)
            m2.metric("Total Lines", f"{res.total_lines:,}")
            m3.metric("Characters", f"{res.total_chars:,} / {res.char_cap:,}")
            m4.metric("Est. Tokens", f"~{res.token_estimate:,}")

            if res.one_hop_links:
                st.subheader("🔗 AST One-Hop Local Import Graph")
                for src_file, deps in res.one_hop_links.items():
                    st.markdown(f"- `{src_file}` imports: {', '.join(f'`{d}`' for d in deps)}")

            # Manifest Table
            st.subheader("📋 Pack Manifest")
            manifest_data = [
                {
                    "Path": item.path,
                    "Size (bytes)": item.bytes,
                    "Status": item.status.upper(),
                    "Reason": item.reason,
                }
                for item in res.manifest
            ]
            st.dataframe(manifest_data, use_container_width=True, height=280)

            # Download Pack Manifest JSON
            cache_pack_path = Path("data/cache/last_pack.json")
            if cache_pack_path.exists():
                st.download_button(
                    "Download Pack Manifest (JSON)",
                    data=cache_pack_path.read_text(encoding="utf-8"),
                    file_name="last_pack.json",
                    mime="application/json",
                )

            # File Preview
            if res.files:
                st.subheader("🔍 File Preview")
                chosen_file = st.selectbox("Select file to view", options=[f.rel_path for f in res.files])
                matched = next((f for f in res.files if f.rel_path == chosen_file), None)
                if matched:
                    tags = []
                    if matched.is_diff_match:
                        tags.append("Changed File")
                    if matched.is_ast_import:
                        tags.append(f"AST Import (from {matched.imported_by})")
                    st.caption(f"{matched.lines} lines | {matched.size_bytes:,} bytes | {', '.join(tags)}")
                    st.code(matched.content, language=matched.extension.replace(".", "") or "text")

            st.divider()
            if st.button("Proceed to Audit ➡️"):
                set_page("Audit")


# --- Page 3: Audit ---
elif st.session_state.active_nav == "Audit":
    st.title("🔍 Multi-Pass AI Auditor")

    if not st.session_state.pack_result:
        st.warning("No files packed. Please pack files on the 'Pack' page before auditing.")
        if st.button("⬅️ Go to Pack"):
            set_page("Pack")
    else:
        res = st.session_state.pack_result
        st.markdown(f"Auditing **{res.total_files} files** ({res.total_chars:,} chars) using **{selected_model}**.")

        st.markdown(
            """
            **Three Distinct Passes:**
            1. **Pass 1: Breaking API / Call-Site Drift** — Detects renamed/removed functions, mismatched calls.
            2. **Pass 2: Security & Credentials** — Detects injection patterns and secrets locations (locations only, no exploits).
            3. **Pass 3: Test Coverage & Regression** — Detects missing unit tests for changed functions.
            """
        )

        if st.button("Run 3-Pass AI Audit", type="primary"):
            progress_bar = st.progress(0)
            status_text = st.empty()

            def update_progress(label: str, percent: int):
                status_text.text(label)
                progress_bar.progress(percent)

            try:
                with st.spinner("Executing separate audit passes with Agnes AI..."):
                    audit_res = run_three_pass_audit(
                        pack_result=res,
                        provider_name=selected_provider_name,
                        model_name=selected_model,
                        progress_callback=update_progress,
                    )
                    st.session_state.audit_result = audit_res
                    status_text.text("Audit complete!")
                    progress_bar.progress(100)
                    st.success(f"Completed! Generated {len(audit_res['findings'])} structured findings. Saved to `data/cache/last_audit.json`.")
            except Exception as exc:
                st.error(f"Audit failed: {exc}")

        if st.session_state.audit_result:
            audit = st.session_state.audit_result
            c1, c2, c3 = st.columns(3)
            c1.metric("API Drift Findings", audit["pass_summaries"].get("breaking_api", 0))
            c2.metric("Security Findings", audit["pass_summaries"].get("security", 0))
            c3.metric("Missing Test Findings", audit["pass_summaries"].get("missing_tests", 0))

            st.divider()
            if st.button("View Findings ➡️"):
                set_page("Findings")


# --- Page 4: Findings ---
elif st.session_state.active_nav == "Findings":
    st.title("📋 Audit Findings")

    # Load from session or cached file
    findings_data = st.session_state.audit_result
    cache_path = Path("data/cache/last_audit.json")

    if not findings_data and cache_path.exists():
        try:
            findings_data = json.loads(cache_path.read_text(encoding="utf-8"))
            st.session_state.audit_result = findings_data
            st.info("Loaded previous audit from `data/cache/last_audit.json`.")
        except Exception:
            pass

    if not findings_data:
        st.warning("No audit report available. Run an audit on the 'Audit' page first.")
        if st.button("⬅️ Go to Audit"):
            set_page("Audit")
    else:
        findings = findings_data.get("findings", [])
        st.markdown(
            f"Audit for **{findings_data.get('repository', 'Unknown')}** | "
            f"Model: `{findings_data.get('model', 'agnes-3.0-flash')}` | "
            f"Total Findings: **{len(findings)}**"
        )

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            severity_filter = st.multiselect(
                "Filter Severity",
                options=["High", "Medium", "Low", "Info"],
                default=["High", "Medium", "Low", "Info"],
            )
        with col_f2:
            pass_filter = st.multiselect(
                "Filter Audit Pass",
                options=["breaking_api", "security", "missing_tests"],
                default=["breaking_api", "security", "missing_tests"],
                format_func=lambda x: {
                    "breaking_api": "Breaking API / Drift",
                    "security": "Security",
                    "missing_tests": "Missing Tests",
                }.get(x, x),
            )

        filtered = [
            f for f in findings
            if f.get("severity", "Medium") in severity_filter and f.get("pass", "breaking_api") in pass_filter
        ]

        st.caption(f"Showing {len(filtered)} of {len(findings)} findings.")

        # Findings Summary Table
        if filtered:
            st.subheader("📊 Findings Table")
            table_records = [
                {
                    "Severity": f.get("severity", "Medium"),
                    "Pass": f.get("pass", ""),
                    "File": f.get("file", ""),
                    "Title": f.get("title", ""),
                    "Recommendation": f.get("recommendation", ""),
                }
                for f in filtered
            ]
            st.dataframe(table_records, use_container_width=True, height=220)

            st.subheader("🔍 Finding Details")
            severity_icons = {
                "High": "🔴",
                "Medium": "🟠",
                "Low": "🟡",
                "Info": "ℹ️",
            }

            for idx, item in enumerate(filtered, start=1):
                icon = severity_icons.get(item.get("severity"), "•")
                title = item.get("title", "Untitled Finding")
                file_path = item.get("file", "Unspecified file")
                severity = item.get("severity", "Medium")

                with st.expander(f"{icon} [{severity}] {title} — {file_path}", expanded=(severity == "High")):
                    st.markdown(f"**File:** `{file_path}`")
                    st.markdown(f"**Evidence Span:**")
                    st.code(item.get("evidence_span", "No span provided"), language="text")
                    st.markdown(f"**Recommendation:** {item.get('recommendation', 'No recommendation')}")
        else:
            st.success("🎉 No findings match the active filters!")

        st.divider()
        st.download_button(
            "Download Findings (JSON)",
            data=json.dumps(findings_data, indent=2),
            file_name="last_audit.json",
            mime="application/json",
        )
