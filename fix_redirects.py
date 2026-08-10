import re

with open(r"E:\Python\CORTEX_AI\Book_Keeping_App\finance\views.py", "r", encoding="utf-8") as f:
    content = f.read()

# Fix all remaining unnamespaced redirects
replacements = {
    "redirect('emi_list')": "redirect('finance:emi_list')",
    "redirect('debts_credits')": "redirect('finance:debts_credits')",
    "redirect('dashboard')": "redirect('finance:dashboard')",
    "redirect('transaction_list')": "redirect('finance:transaction_list')",
    "redirect('export_page')": "redirect('finance:export_page')",
    "'emi_list')": "'finance:emi_list')",  # for the HTTP_REFERER fallback
}

for old, new in replacements.items():
    if old in content:
        count = content.count(old)
        content = content.replace(old, new)
        print(f"Replaced {count}x: {old} -> {new}")

with open(r"E:\Python\CORTEX_AI\Book_Keeping_App\finance\views.py", "w", encoding="utf-8") as f:
    f.write(content)

print("\nDone! Verifying...")

# Verify no unnamespaced redirects remain
import re
remaining = re.findall(r"redirect\('[a-z_]+'", content)
if remaining:
    print(f"WARNING: Still found unnamespaced: {remaining}")
else:
    print("All redirects properly namespaced!")
