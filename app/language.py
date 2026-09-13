"""Explicit bilingual search aliases; unknown text is preserved for source search."""
import re
SEARCH_ALIASES = {
    '日式北欧': 'Japandi', '北欧风': 'Scandinavian', '北欧': 'Scandinavian', '日式': 'Japandi',
    '侘寂': 'Wabi-Sabi', '极简': 'Minimalist', '工业风': 'Industrial', '现代': 'Modern', '当代': 'Contemporary',
    '混搭': 'Eclectic', '浅色橡木': 'oak', '浅橡木': 'oak', '胡桃木': 'walnut', '暖木': 'wood', '暖色木材': 'wood',
    '木材': 'wood', '木质': 'wood', '大理石': 'marble', '石材': 'stone', '藤编': 'rattan', '拱形': 'arch',
    '奶油色': 'cream', '大地色': 'earthy', '彩色': 'colourful', '多彩': 'colourful', '缤纷': 'colourful',
    '深色': 'dark', '白色': 'white', '客厅': 'living room', '卧室': 'bedroom', '厨房': 'kitchen',
    '收纳': 'storage', '组屋': 'HDB', '公寓': 'condo', '有地住宅': 'landed', '灯光': 'lighting', '自然光': 'daylight'}

def normalize_search(text):
    if not re.search(r'[\u4e00-\u9fff]', text):
        return text.strip()
    for key in sorted(SEARCH_ALIASES, key=len, reverse=True):
        text = text.replace(key, ' ' + SEARCH_ALIASES[key] + ' ')
    text = re.sub('我想要|我喜欢|我想找|我想看|帮我找|请搜索|搜索|看看|想要|喜欢|风格|的|和|与', ' ', text)
    return ' '.join(text.split())[:100]
