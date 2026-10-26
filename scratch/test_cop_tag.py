import html

def format_cop_messages(members, message_text=""):
    safe_message_text = html.escape(message_text) if message_text else ""
    batch_size = 5
    results = []
    
    for i in range(0, len(members), batch_size):
        batch = members[i:i+batch_size]
        tags = []
        for telegram_id, username, codename in batch:
            safe_codename = html.escape(codename)
            tags.append(f'<a href="tg://user?id={telegram_id}">{safe_codename}</a>')
            
        tag_str = ", ".join(tags)
        final_msg = ""
        if safe_message_text:
            final_msg += f"{safe_message_text}\n\n"
        final_msg += f"📢 {tag_str}"
        results.append(final_msg)
        
    return results

# Test cases
sample_members = [
    (1001, "@alice", "ALICE"),
    (1002, "bob_the_builder", "BOB & FRIENDS"),
    (1003, "", "<CHARLIE>"),
    (1004, None, "DAVID"),
    (1005, "@eva", "EVA"),
    (1006, "@frank", "FRANK"),
]

messages_without_text = format_cop_messages(sample_members)
assert len(messages_without_text) == 2, f"Expected 2 batches, got {len(messages_without_text)}"
assert '📢 <a href="tg://user?id=1001">ALICE</a>, <a href="tg://user?id=1002">BOB &amp; FRIENDS</a>, <a href="tg://user?id=1003">&lt;CHARLIE&gt;</a>, <a href="tg://user?id=1004">DAVID</a>, <a href="tg://user?id=1005">EVA</a>' in messages_without_text[0]
assert '📢 <a href="tg://user?id=1006">FRANK</a>' in messages_without_text[1]

messages_with_text = format_cop_messages(sample_members, "Pengumuman Rapat <Urgent> & Penting")
assert "Pengumuman Rapat &lt;Urgent&gt; &amp; Penting\n\n📢" in messages_with_text[0]

print("All QA assertions passed successfully!")
