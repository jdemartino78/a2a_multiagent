from flask import Flask, jsonify, request
import json
import os

app = Flask(__name__)

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))

# Construct the full path to agent_registry.json
# It's now in the parent directory's 'host_agent' folder
json_path = os.path.join(script_dir, '..', 'host_agent', 'agent_registry.json')

# Load the agent registry from the JSON file
with open(json_path, 'r') as f:
    agent_registry = json.load(f)

@app.route('/agents', methods=['GET'])
def get_agents():
    """
    Returns a list of agent cards.
    Can be filtered by tenant_id.
    """
    tenant_id = request.args.get('tenant_id')
    print(f"\n--- Agent Registry: Received request for tenant_id: {tenant_id} ---")

    if not tenant_id:
        # Return all agents that do not have a tenant_id tag
        non_tenant_agents = []
        for agent in agent_registry:
            is_tenant_specific = False
            if 'skills' in agent:
                for skill in agent['skills']:
                    if 'tags' in skill:
                        for tag in skill['tags']:
                            if tag.startswith('tenant_id:'):
                                is_tenant_specific = True
                                break
                    if is_tenant_specific:
                        break
            if not is_tenant_specific:
                non_tenant_agents.append(agent)
        print(f"Found non-tenant agents: {[agent['name'] for agent in non_tenant_agents]}")
        return jsonify(non_tenant_agents)

    # Filter agents by tenant_id
    # This logic now correctly includes both agents specific to the tenant
    # and global agents (those without any tenant_id tag).
    filtered_agents = []
    for agent in agent_registry:
        print(f"Processing agent: {agent.get('name', 'Unknown')}")
        is_tenant_specific = False
        matches_tenant = False
        is_global = True

        if 'skills' in agent:
            for skill in agent['skills']:
                if 'tags' in skill:
                    for tag in skill['tags']:
                        if tag.startswith('tenant_id:'):
                            is_global = False
                            is_tenant_specific = True
                            if tag == f'tenant_id:{tenant_id}':
                                matches_tenant = True
                                break
                if matches_tenant:
                    break
        
        if matches_tenant:
            print(f"  -> Included: Matches tenant_id '{tenant_id}'")
            filtered_agents.append(agent)
        elif is_global and not is_tenant_specific:
            print("  -> Included: Is a global agent.")
            filtered_agents.append(agent)
        else:
            print("  -> Excluded.")

    final_agent_names = [agent['name'] for agent in filtered_agents]
    print(f"--- Agent Registry: Returning agents: {final_agent_names} ---\n")
    return jsonify(filtered_agents)

if __name__ == '__main__':
    app.run(debug=True, port=5001)
