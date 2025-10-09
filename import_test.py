# import_test.py
import sys
print("Python Path:", sys.path)

try:
    from horizon_agent.adk_agent_executor import HorizonAgentExecutor
    print("Successfully imported HorizonAgentExecutor!")
except ImportError as e:
    print("Failed to import HorizonAgentExecutor.")
    print("Error:", e)
except Exception as e:
    print("An unexpected error occurred.")
    print("Error:", e)
