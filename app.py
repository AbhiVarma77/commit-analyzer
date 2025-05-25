import streamlit as st
import requests
import json
from datetime import datetime, timedelta
from collections import Counter, defaultdict
import re
import time
from textblob import TextBlob
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Configure page
st.set_page_config(
    page_title="GitLab Team Member Analyzer",
    page_icon="👥",
    layout="wide"
)

# Initialize session state
if 'commits_data' not in st.session_state:
    st.session_state.commits_data = []
if 'team_analysis' not in st.session_state:
    st.session_state.team_analysis = {}
def make_api_request(url, headers, params=None, timeout=30):
    """Make API request with error handling"""
    try:
        response = requests.get(url, headers=headers, params=params, timeout=timeout)
        if response.status_code == 200:
            return response.json(), None
        else:
            error_msg = f"HTTP {response.status_code}"
            try:
                error_data = response.json()
                error_msg += f": {error_data}"
            except:
                error_msg += f": {response.text[:200]}"
            return None, error_msg
    except requests.exceptions.RequestException as e:
        return None, f"Request failed: {str(e)}"

def fetch_all_commits(group_id_or_path, token, since_date=None, max_projects=20):
    """Fetch commits from all projects in the group"""
    headers = {"PRIVATE-TOKEN": token}
    
    # Get projects in group (pagination handling)
    projects = []
    page = 1
    per_page = 50
    base_url = "https://code.swecha.org/api/v4"
    while True:
        params = {'page': page, 'per_page': per_page}
        url = f"{base_url}/groups/{group_id_or_path}/projects"
        data, err = make_api_request(url, headers, params)
        if err:
            st.error(f"Error fetching projects: {err}")
            return []
        if not data:
            break
        projects.extend(data)
        if len(data) < per_page or len(projects) >= max_projects:
            break
        page += 1

    projects = projects[:max_projects]
    all_commits = []
    for project in projects:
        project_id = project['id']
        project_name = project['path_with_namespace']
        page = 1
        while True:
            params = {'page': page, 'per_page': 100}
            if since_date:
                params['since'] = since_date.isoformat()
            url = f"{base_url}/projects/{project_id}/repository/commits"
            commits, err = make_api_request(url, headers, params)
            if err:
                st.warning(f"Error fetching commits for project {project_name}: {err}")
                break
            if not commits:
                break
            for commit in commits:
                commit['project_name'] = project_name
            all_commits.extend(commits)
            if len(commits) < 100:
                break
            page += 1
        time.sleep(0.2)  # To avoid hitting rate limits
    return all_commits

def categorize_commit_message(message):
    """Basic categorization of commit messages"""
    message = message.lower()
    if re.search(r'\bfix(es|ed)?\b', message):
        return "Bug Fix"
    elif re.search(r'\bfeature\b|\badd(ed)?\b', message):
        return "Feature"
    elif re.search(r'\brefactor(ed)?\b', message):
        return "Refactor"
    elif re.search(r'\bdoc(s|umentation)?\b', message):
        return "Documentation"
    elif re.search(r'\btest(s|ing)?\b', message):
        return "Tests"
    else:
        return "Other"

def analyze_team_members(commits):
    """Analyze commits per team member"""
    team_analysis = {}
    for commit in commits:
        author_name = commit.get('author_name', 'Unknown')
        if author_name not in team_analysis:
            team_analysis[author_name] = {
                'commits': [],
                'stats': {
                    'total_commits': 0,
                    'projects': set(),
                    'categories': defaultdict(int),
                }
            }
        team_analysis[author_name]['commits'].append(commit)
        team_analysis[author_name]['stats']['total_commits'] += 1
        team_analysis[author_name]['stats']['projects'].add(commit.get('project_name', 'Unknown'))
        category = categorize_commit_message(commit.get('title', commit.get('message', '')))
        team_analysis[author_name]['stats']['categories'][category] += 1
    
    # Convert projects sets to counts and generate summary markdown
    for member, data in team_analysis.items():
        data['stats']['projects'] = len(data['stats']['projects'])
        # Compose summary markdown for member
        total = data['stats']['total_commits']
        projects = data['stats']['projects']
        categories = data['stats']['categories']
        summary_lines = [
            f"## {member}",
            f"- Total Commits: **{total}**",
            f"- Projects Contributed To: **{projects}**",
            "- Commit Categories:",
        ]
        for cat, count in categories.items():
            summary_lines.append(f"  - {cat}: {count}")
        data['summary'] = "\n".join(summary_lines)
    return team_analysis

def create_team_overview_dashboard(team_analysis):
    """Create a visual dashboard for team overview"""
    if not team_analysis:
        st.warning("No team data to display")
        return
    st.header("👥 Team Overview Dashboard")

    # Team statistics
    total_members = len(team_analysis)
    total_commits = sum(member['stats']['total_commits'] for member in team_analysis.values())
    total_projects = len(set(
        project for member in team_analysis.values() 
        for commit in member['commits'] 
        for project in [commit.get('project_name', 'Unknown')]
    ))

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Team Members", total_members)
    with col2:
        st.metric("Total Commits", total_commits)
    with col3:
        st.metric("Active Projects", total_projects)
    with col4:
        avg_commits = total_commits / total_members if total_members > 0 else 0
        st.metric("Avg Commits/Member", f"{avg_commits:.1f}")

    # Member contribution chart
    st.subheader("📊 Member Contributions")
    member_data = []
    for member, data in team_analysis.items():
        member_data.append({
            'Member': member,
            'Commits': data['stats']['total_commits'],
            'Projects': data['stats']['projects']
        })
    df = pd.DataFrame(member_data)
    col1, col2 = st.columns(2)
    with col1:
        fig_commits = px.bar(df, x='Member', y='Commits', title='Commits per Member')
        fig_commits.update_xaxes(tickangle=45)
        st.plotly_chart(fig_commits, use_container_width=True)
    with col2:
        fig_projects = px.bar(df, x='Member', y='Projects', title='Projects per Member')
        fig_projects.update_xaxes(tickangle=45)
        st.plotly_chart(fig_projects, use_container_width=True)

    # Category distribution across team
    st.subheader("🏷️ Work Distribution Across Team")
    all_categories = defaultdict(int)
    for member_data in team_analysis.values():
        for category, count in member_data['stats']['categories'].items():
            all_categories[category] += count
    if all_categories:
        categories_df = pd.DataFrame(list(all_categories.items()), columns=['Category', 'Count'])
        fig_categories = px.pie(categories_df, values='Count', names='Category', title='Team Work Distribution')
        st.plotly_chart(fig_categories, use_container_width=True)

# Main Streamlit App
st.title("👥 GitLab Team Member Contribution Analyzer")
st.markdown("**Analyze individual team member contributions with detailed insights and summaries**")

# Sidebar configuration
st.sidebar.header("⚙️ Configuration")
group_id = st.sidebar.text_input(
    "Group/Team ID or Path", 
    placeholder="e.g., 123 or myteam/subgroup",
    help="Enter the numeric ID or full path of your GitLab group"
)
token = st.sidebar.text_input(
    "Private Access Token", 
    type="password",
    help="GitLab token with read_api and read_repository permissions"
)
st.sidebar.markdown("---")

# Filters
st.sidebar.subheader("🔧 Analysis Filters")
use_date_filter = st.sidebar.checkbox("Filter by date")
since_date = None
if use_date_filter:
    since_date = st.sidebar.date_input("Since date", value=datetime.now() - timedelta(days=90))
max_projects = st.sidebar.number_input("Max projects to analyze", min_value=1, max_value=100, value=20)

# Analysis button
if st.sidebar.button("🚀 Analyze Team", type="primary", use_container_width=True):
    if not group_id or not token:
        st.error("❌ Please provide both Group ID and Access Token")
    else:
        # Clear previous data
        st.session_state.commits_data = []
        st.session_state.team_analysis = {}
        # Test authentication
        headers = {"PRIVATE-TOKEN": token}
        test_url = "https://code.swecha.org/api/v4/user"
        test_data, test_error = make_api_request(test_url, headers)
        if not test_data:
            st.error("❌ Authentication failed! Please check your token.")
            st.stop()
        st.success("✅ Authentication successful!")
        # Fetch commits
        st.info("🔄 Fetching commits from all team projects...")
        commits = fetch_all_commits(group_id, token, since_date, max_projects)
        if commits:
            st.session_state.commits_data = commits
            st.success(f"🎉 Found {len(commits)} commits total")
            # Analyze team members
            st.info("🔍 Analyzing individual team member contributions...")
            team_analysis = analyze_team_members(commits)
            st.session_state.team_analysis = team_analysis
            st.success(f"✅ Analysis complete for {len(team_analysis)} team members!")
        else:
            st.error("❌ No commits found!")

# Display results
if st.session_state.team_analysis:
    st.markdown("---")
    # Team overview dashboard
    create_team_overview_dashboard(st.session_state.team_analysis)
    st.markdown("---")
    # Individual member analysis
    st.header("👤 Individual Team Member Analysis")
    selected_member = st.selectbox(
        "Select team member to analyze:",
        options=list(st.session_state.team_analysis.keys()),
        index=0
    )
    if selected_member:
        member_data = st.session_state.team_analysis[selected_member]
        # Display member summary
        st.markdown(member_data['summary'])
        # Download individual summary
        col1, col2 = st.columns([1, 1])
        with col1:
            st.download_button(
                label=f"📄 Download {selected_member}'s Summary",
                data=member_data['summary'],
                file_name=f"{selected_member.replace(' ', '_')}_contribution_summary_{datetime.now().strftime('%Y%m%d')}.md",
                mime="text/markdown"
            )
        with col2:
            if st.button("📊 Show Detailed Commits"):
                st.subheader(f"📝 All Commits by {selected_member}")
                commits_df = []
                for commit in member_data['commits']:
                    commits_df.append({
                        'Date': commit.get('created_at', '')[:10],
                        'Project': commit.get('project_name', 'Unknown'),
                        'Message': commit.get('title', commit.get('message', 'No message')),
                        'Category': categorize_commit_message(commit.get('title', commit.get('message', '')))
                    })
                if commits_df:
                    df = pd.DataFrame(commits_df)
                    st.dataframe(df, use_container_width=True)

# Help section
if not st.session_state.team_analysis and not st.session_state.commits_data:
    st.markdown("---")
    st.info("👆 **Enter your Team/Group ID and Access Token to analyze individual team member contributions**")
    with st.expander("🆘 Setup Instructions"):
        st.markdown("""
        ### Getting Your Access Token:
        1. Go to your GitLab instance (code.swecha.org)
        2. Click your avatar → **Edit Profile**
        3. Go to **Access Tokens** in the sidebar
        4. Create token with scopes: `read_api`, `read_repository`
        ### Finding Your Team/Group ID:
        - **Numeric ID**: Found on the group's main page
        - **Path**: Use full path like `mycompany/development-team`
        - **From URL**: Extract from `https://code.swecha.org/groups/your-team-name`
        ### What You'll Get:
        - 📊 **Team Overview**: Visual dashboard with contribution metrics
        - 👤 **Individual Analysis**: Detailed summary for each team member
        - 🏷️ **Work Categorization**: Automatic classification of contributions
        - 📈 **Activity Patterns**: Working hours and day preferences
        - 💡 **Growth Insights**: Personalized recommendations for each member
        - 📄 **Exportable Reports**: Download individual contribution summaries
        """)

st.markdown("---")
st.markdown("🚀 **Enhanced Team Analytics** | 👥 **Individual Contributor Insights** | 📊 **Powered by GitLab API**")
