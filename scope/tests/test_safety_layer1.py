import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from scope.observability_tools import safety_check_layer1

def test_safety_check():
    print("Testing Safety Layer 1 (Toxic-BERT)...")
    
    # Test Case 1: Safe Input
    safe_input = "Hello, I would like to check my account balance."
    print(f"\nTesting Safe Input: '{safe_input}'")
    result_safe = safety_check_layer1(safe_input)
    print(f"Result: {result_safe}")
    
    if "PASSED" in result_safe:
        print("✅ Safe input passed correctly.")
    else:
        print("❌ Safe input failed unexpectedly.")

    # Test Case 2: Toxic Input
    # Using a standard toxic phrase for testing models (warning: offensive content)
    toxic_input = "You are stupid and I hate you."
    print(f"\nTesting Toxic Input: '{toxic_input}'")
    result_toxic = safety_check_layer1(toxic_input)
    print(f"Result: {result_toxic}")
    
    if "FAILED" in result_toxic:
        print("✅ Toxic input blocked correctly.")
    else:
        print("❌ Toxic input was not blocked.")

if __name__ == "__main__":
    test_safety_check()
