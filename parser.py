import re

def convert_insert_to_update(input_path, output_path):
    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 정규식으로 INSERT 문 파싱
    pattern = re.compile(
        r"INSERT INTO track\s*\(\s*id\s*,\s*mv_url\s*\)\s*VALUES\s*\(\s*'(?P<id>[^']+)'\s*,\s*'(?P<mv_url>[^']+)'\s*\)\s*ON DUPLICATE KEY UPDATE\s*mv_url\s*=\s*VALUES\(mv_url\);",
        re.IGNORECASE
    )

    updates = []
    for match in pattern.finditer(content):
        track_id = match.group("id")
        mv_url = match.group("mv_url")
        update_stmt = f"UPDATE track SET mv_url = '{mv_url}' WHERE id = '{track_id}';"
        updates.append(update_stmt)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(updates))

    print(f"✅ 변환 완료! {len(updates)}개의 UPDATE 문이 '{output_path}'에 저장되었습니다.")

# 사용 예시
convert_insert_to_update('input.sql', 'output.sql')
