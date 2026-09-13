"""Optional, conditional detail questions. Answers never replace the eight core decisions."""
from copy import deepcopy

# id | dimension | role | eligible core values (* = any confirmed value) | EN | ZH | bilingual choices
_ROWS = '''
seating|function|homeowner|family_relaxing,hosting|How should people sit together?|你希望大家怎样坐在一起？|One shared sofa~一张共用沙发;Separate seats~独立座椅;Flexible mix~灵活组合
media|function|homeowner|tv_and_media|How prominent should the screen be?|屏幕在空间中应该多显眼？|Main focal point~视觉中心;Blend into cabinetry~融入柜体;Hide when unused~不用时隐藏
retreat|function|homeowner|quiet_retreat|What makes a quiet retreat work for you?|怎样的安静角落最适合你？|Reading corner~阅读角;View of greenery~绿植窗景;Space to stretch~舒展身体的空间
flexibility|function|homeowner|flexible_use|Which change of activity should be easiest?|哪种活动切换最需要方便？|Work to relaxing~工作与休息;Solo to guests~独处与待客;Play to tidy~玩耍与收纳
hosting_size|function|homeowner|hosting|What gathering feels typical?|平时更常见哪种聚会？|Two or three friends~两三位朋友;Small group~小型聚会;Extended family~大家庭相聚
family_activity|function|homeowner|family_relaxing|What would bring everyone together?|什么活动能让家人聚在一起？|Talking~聊天;Games~游戏;Reading side by side~各自阅读相互陪伴
wood_grain|material|homeowner|light_oak,walnut|How visible should the timber grain be?|你希望木纹有多明显？|Quiet and even~细腻均匀;Natural variation~自然变化;Strong character~鲜明木纹
stone_finish|material|homeowner|stone|Which stone finish feels right?|哪种石材表面更合心意？|Honed matte~磨砂哑光;Polished~抛光;Textured~有肌理
metal_finish|material|homeowner|metal|Which metal expression do you prefer?|你喜欢怎样的金属质感？|Brushed~拉丝;Darkened~深色;Polished~抛光
textile_touch|material|homeowner|soft_textiles|How should fabrics feel?|你希望织物摸起来怎样？|Smooth~平滑;Soft and plush~柔软蓬松;Woven texture~明显织纹
material_mix|material|homeowner|*|How many material voices should be visible?|空间里材料的种类感应该多强？|One dominant material~一种材料主导;Two in balance~两种平衡;Layered variety~多种层次
colour_contrast|colour|homeowner|*|How much contrast would you enjoy?|你喜欢多强的色彩对比？|Almost tonal~接近同色系;A few accents~少量点缀;Strong contrast~鲜明对比
accent_location|colour|homeowner|*|Where would you introduce accent colour?|你想把点缀色放在哪里？|Movable objects~可移动物件;Textiles~织物;One wall~一面墙
colour_temperature|colour|homeowner|warm_neutral,light_neutral,earthy|How warm should the neutrals feel?|中性色应该有多温暖？|Creamy~奶油色调;Balanced~中性平衡;Grey leaning~偏灰色调
night_scene|lighting|homeowner|*|What should evening light invite you to do?|晚间灯光应该让你想做什么？|Wind down~放松休息;Talk together~一起聊天;Read comfortably~舒适阅读
light_control|lighting|homeowner|*|How would you like to change the atmosphere?|你想怎样调整光线氛围？|One simple setting~一种简单设置;Separate zones~分区控制;Several scenes~多种场景
daylight_privacy|lighting|homeowner|natural_bright|How should daylight and privacy coexist?|你希望怎样兼顾自然光与隐私？|Sheer filtering~纱帘柔化;Adjustable layers~多层可调;Open view when home~在家时开放视野
fixture_presence|lighting|homeowner|statement,soft_layered,warm_ambient|How visible should the fittings be?|你希望灯具本身有多显眼？|Mostly concealed~尽量隐藏;Quiet objects~低调造型;Sculptural feature~雕塑般的主角
silhouette|style|homeowner|*|Which furniture outline draws you in?|哪种家具轮廓更吸引你？|Straight lines~直线;Soft curves~柔和曲线;A mix~两者结合
visual_density|style|homeowner|*|How much should be on display?|你希望空间里展示多少东西？|Very little~很少;A few meaningful pieces~少量有意义的物件;Collected layers~丰富收藏层次
personal_objects|style|homeowner|*|What deserves a place in the design?|哪些个人物品应融入设计？|Books~书籍;Art~艺术品;Travel and family objects~旅行与家庭纪念物
symmetry|style|homeowner|*|Which composition feels more natural?|哪种构图让你更自在？|Balanced symmetry~平衡对称;Relaxed asymmetry~轻松不对称;No preference~没有偏好
calm_detail|mood|homeowner|calm|What most helps you feel calm?|什么最能让你平静？|Clear surfaces~整洁台面;Soft sound~柔和声音;Natural textures~自然肌理
cosy_detail|mood|homeowner|cosy|What creates cosiness for you?|什么让你觉得温馨？|Enveloping seating~有包裹感的座椅;Warm pools of light~局部暖光;Layered textiles~层叠织物
bright_detail|mood|homeowner|bright|What does bright mean to you?|你说的明亮主要是什么？|Plenty of daylight~充足自然光;Light surfaces~浅色表面;Lively colour~活泼色彩
social_detail|mood|homeowner|social|What makes conversation feel easy?|怎样的空间更容易聊天？|Face to face~面对面;Loose seating circle~松散围坐;Linked dining and living~餐厅与客厅相连
focal_point|mood|homeowner|dramatic|What should make the strongest impression?|什么应该留下最强烈的印象？|Art~艺术品;Lighting~灯光;Material surface~材料表面
sound|mood|homeowner|*|What sound environment suits your routine?|哪种声音环境适合你的日常？|Quiet~安静;Background music~背景音乐;Lively household~热闹家庭
daily_reset|function|homeowner|*|How should the room reset after use?|使用之后你希望怎样恢复整洁？|Put everything away~全部收起;Leave everyday items handy~常用物品留在手边;Flexible lived-in look~允许自然生活痕迹
seating_posture|function|homeowner|*|How do you usually relax?|你通常怎样休息？|Sit upright~端坐;Curl up~蜷坐;Stretch out~躺靠伸展
greenery|mood|homeowner|*|How should greenery enter the room?|你想怎样把绿意带进客厅？|A few plants~少量植物;A planted corner~植物角;Only the outside view~仅保留窗外绿景
entry_route|layout|designer|*|What should the entry route prioritise?|入口动线优先照顾什么？|Direct circulation~直接通行;A transition space~过渡空间;Storage on arrival~入户收纳
storage_access|layout|designer|storage_led,compact|Which storage access best fits the routine?|哪种收纳方式更符合生活习惯？|Open daily shelves~日常开放架;Closed fronts~封闭柜门;Mixed access~开放与封闭结合
zoning_boundary|layout|designer|zoned,conversation_focused|How should activity zones be defined?|活动分区应该怎样界定？|Furniture placement~家具摆放;Rug and lighting~地毯与灯光;Partial divider~局部隔断
flow_anchor|layout|designer|open_flow|What can anchor the room without closing it?|什么能在保持开放时界定客厅？|A rug~地毯;A sofa arrangement~沙发布局;A ceiling light~吊灯
route_review|layout|designer|*|Which movement needs a site check first?|哪种通行最先需要现场核对？|Balcony access~阳台通行;Entrance to seating~入口到座位;Access around furniture~家具周围通行
existing_items|layout|designer|*|How should existing furniture be handled?|现有家具怎样处理？|Keep the main pieces~保留主要家具;Keep selected pieces~保留部分家具;Review with homeowner~与业主一起确认
sightlines|layout|designer|*|Which view should guide the arrangement?|哪条视线应引导布局？|Window view~窗景;Conversation~对话视线;Screen visibility~屏幕可视性
outlets|layout|designer|*|What should be checked before fixing positions?|确定位置前先核对什么？|Power and data~电源与网络;Door swings~门的开启范围;Actual furniture dimensions~家具实际尺寸
surface_care|maintenance|designer|*|Which cleaning routine should finishes support?|饰面应适应怎样的清洁习惯？|Quick daily wipe~日常快速擦拭;Weekly attention~每周打理;Specialist care accepted~接受专业养护
wear|maintenance|designer|*|Which wear pattern deserves most attention?|最需要关注哪种使用磨损？|Frequent touch~频繁触摸;Spills~液体泼洒;Pets and play~宠物与玩耍
repair|maintenance|designer|*|Which ageing approach fits the homeowner?|哪种老化方式更符合业主期待？|Patina welcomed~接受自然旧化;Keep uniform appearance~保持均匀外观;Replaceable components~部件可更换
fabric_care|maintenance|designer|*|How should upholstery care be approached?|软包清洁怎样安排？|Removable covers~可拆洗布套;Wipeable surfaces~可擦拭表面;Specialist cleaning~专业清洗
sample_review|maintenance|designer|*|What should material samples help verify?|材料样品最应帮助验证什么？|Touch and glare~触感与反光;Colour in the room~室内实际颜色;Cleaning compatibility~清洁方式适配
ventilation|layout|designer|*|What should the site review document about airflow?|现场踏勘应记录哪些通风情况？|Window operation~窗户开启;Furniture obstruction~家具遮挡;Existing air-conditioning~现有空调
handover|layout|designer|*|What would make the next design discussion clearest?|下次设计讨论用什么最清楚？|Annotated plan~带注释的平面图;Material samples~材料样品;Two contrasting layouts~两套对比布局
'''
DETAIL_QUESTIONS = []
for row in _ROWS.strip().splitlines():
    key, dimension, role, values, en, zh, choices = row.split('|')
    pairs = [item.split('~') for item in choices.split(';')]
    DETAIL_QUESTIONS.append(dict(id='detail_' + key, dimension=dimension, target=role,
        requires=values.split(','), prompt=en, promptZh=zh,
        options=[p[0] for p in pairs], optionsZh={p[0]: p[1] for p in pairs},
        rationale='This refines your confirmed preference into a decision you can discuss together.',
        rationaleZh='这道题把已确认的偏好进一步细化为可以共同讨论的设计决定。', impact=0.6, detail=True))

# A second level follows detail answers, rather than exhausting a static questionnaire.
_REFINEMENTS = [
 ('curve_placement', 'style', 'silhouette', 'Soft curves', 'Where should the curves be most visible?', '你希望曲线主要出现在哪里？', [('Seating','座椅'),('Tables','桌子'),('Joinery','定制柜体')]),
 ('display_grouping', 'style', 'visual_density', 'Collected layers', 'How should your collected objects be grouped?', '你想怎样组织收藏物件？', [('By story','按故事'),('By colour','按色彩'),('Loosely mixed','自由混合')]),
 ('book_access', 'style', 'personal_objects', 'Books', 'Which books should be easiest to reach?', '哪些书应该最容易拿到？', [('Everyday reading','日常读物'),('Shared family books','家庭共读'),('Display editions','展示书籍')]),
 ('grain_direction', 'material', 'wood_grain', 'Strong character', 'How should strong grain run across surfaces?', '鲜明木纹在表面上怎样延续？', [('Continuous direction','方向连续'),('Separate framed panels','分块框定'),('Compare samples first','先比较样品')]),
 ('accent_change', 'colour', 'accent_location', 'Movable objects', 'How often would you like to change these accents?', '你希望多久更换这些可移动点缀？', [('Seasonally','随季节'),('Occasionally','偶尔'),('Keep a lasting set','长期保留一组')]),
 ('scene_priority', 'lighting', 'light_control', 'Several scenes', 'Which lighting scene should be your default?', '哪种灯光场景应作为默认？', [('Arriving home','回到家'),('Evening relaxing','晚间休息'),('Family gathering','家庭相聚')]),
 ('separate_seats', 'function', 'seating', 'Separate seats', 'What should independent seats allow?', '独立座椅应该支持什么？', [('Turning to talk','转向聊天'),('Moving to the window','移到窗边'),('Personal reading','个人阅读')]),
 ('open_storage', 'layout', 'storage_access', 'Open daily shelves', 'Which objects should stay within reach?', '哪些物件应该保持随手可取？', [('Daily essentials','日常用品'),('Books and hobbies','书籍与爱好用品'),('Children’s items','儿童物品')]),
 ('repair_parts', 'maintenance', 'repair', 'Replaceable components', 'Which replaceable part should be prioritised?', '优先考虑哪个可替换部分？', [('Upholstery','软包'),('Cabinet fronts','柜门'),('Hardware','五金')]),
]
for key, dim, parent, value, en, zh, pairs in _REFINEMENTS:
    base = next(q for q in DETAIL_QUESTIONS if q['id'] == 'detail_' + parent)
    DETAIL_QUESTIONS.append(dict(id='detail_' + key, dimension=dim, target=base['target'],
        requires=base['requires'], after={'questionId':base['id'], 'value':value},
        prompt=en, promptZh=zh, options=[p[0] for p in pairs], optionsZh=dict(pairs),
        rationale='Your earlier detail answer makes this the next useful distinction.',
        rationaleZh='你刚才的细节选择，让这一层区分更值得继续讨论。', impact=.8, detail=True))

def eligible(question, confirmed, answers=()):
    value = confirmed.get(question['dimension'])
    if not value or not ('*' in question['requires'] or value in question['requires']):
        return False
    parent = question.get('after')
    return not parent or any(a['questionId'] == parent['questionId'] and a['value'] == parent['value']
                             and a.get('basis') == value for a in answers)

def active_details(state):
    confirmed = {a['dimension']: a['value'] for a in state['attributes'] if a['status'] == 'confirmed'}
    result = []
    for answer in state['answers']:
        if not answer.get('detail') or answer['value'] == 'not_sure':
            continue
        item = deepcopy(answer)
        question = next(q for q in DETAIL_QUESTIONS if q['id'] == answer['questionId'])
        item['needsReview'] = confirmed.get(answer['dimension']) != answer.get('basis') or not eligible(question, confirmed, state['answers'])
        result.append(item)
    return result
