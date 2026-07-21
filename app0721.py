import re
import random
import time
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from google import genai


# ======================================
# 便利な関数
# ======================================
def hex_to_rgba(hex_str, opacity=0.3):
    hex_str = hex_str.lstrip("#")
    if len(hex_str) == 6:
        r = int(hex_str[0:2], 16)
        g = int(hex_str[2:4], 16)
        b = int(hex_str[4:6], 16)
        return f"rgba({r}, {g}, {b}, {opacity})"
    return hex_str


def calculate_power(stats, element, mat1, mat2, custom_word):
    """
    属性・素材の組み合わせ、および隠し味のテキスト特徴から戦闘力を計算するエンジン
    """
    base_power = stats["攻撃"] + stats["耐久"] + stats["素早さ"] + stats["賢さ"] + int(stats["HP"] / 50)

    length_bonus = len(custom_word) * 25

    kanji_count = len(re.findall(r'[\u4e00-\u9fff]', custom_word))
    katakana_count = len(re.findall(r'[\u30a0-\u30ff]', custom_word))
    exclamation_count = custom_word.count("！") + custom_word.count("!")

    word_multiplier = 1.0 + (kanji_count * 0.05) + (katakana_count * 0.03) + (exclamation_count * 0.1)

    element_multiplier = 1.15
    if mat1 == mat2:
        element_multiplier += 0.2  # 同素材純血ボーナス
    if element in ["サイバー", "闇", "光"]:
        element_multiplier += 0.1  # 特殊属性ボーナス

    total_power = int((base_power + length_bonus) * word_multiplier * element_multiplier)

    breakdown = {
        "基礎": base_power,
        "言葉加算": length_bonus,
        "言葉倍率": f"x{word_multiplier:.2f}",
        "属性倍率": f"x{element_multiplier:.2f}"
    }

    return total_power, breakdown


def calculate_rarity(power, custom_word, mat1, mat2):
    """
    戦闘力や珍しい単語・素材コンボからレアリティを判定
    """
    rare_keywords = ["神", "竜", "ドラゴン", "極", "宇宙", "伝説", "究極", "爆発", "覚醒", "光", "闇", "フェニックス", "ブラックホール"]
    combo_text = custom_word + mat1 + mat2
    has_rare_word = any(word in combo_text for word in rare_keywords)

    if power >= 5000 or (power >= 4200 and has_rare_word):
        return "UR", "badge-ur", "card-ur"
    elif power >= 3500:
        return "SSR", "badge-ssr", "card-ssr"
    elif power >= 2500:
        return "SR", "badge-sr", "card-sr"
    else:
        return "R", "badge-r", "card-r"


# ======================================
# ページ基本設定 & セッション保存
# ======================================
st.set_page_config(
    page_title="AIモンスター",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)

if "collection" not in st.session_state:
    st.session_state["collection"] = []

api_key = st.secrets.get("GEMINI_API_KEY", "")

# ======================================
# 完全ダークテーマ固定（ライトモード対応） CSS
# ======================================
st.markdown(
    """
<style>
/* 端末やブラウザがライトモードの場合でも背景と基本文字色を固定 */
html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
    background-color: #0f111a !important;
    color: #e6e6e6 !important;
    font-family: 'Helvetica Neue', Arial, sans-serif;
}

/* Streamlit基本要素（段落・ラベル・ヘッダー）の視認性確保 */
p, span, label, h1, h2, h3, h4, h5, h6, div {
    color: #e6e6e6;
}

[data-testid="stSidebar"] {
    background-color: #151824 !important;
}

[data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] label {
    color: #e6e6e6 !important;
}

/* モンスターカード共通スタイル */
.monster-card {
    border-radius: 16px;
    padding: 24px;
    color: #ffffff !important;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
    text-align: center;
    margin-bottom: 20px;
    border: 2px solid rgba(255, 255, 255, 0.2);
    position: relative;
    overflow: hidden;
    transition: transform 0.3s ease;
}

.monster-card * {
    color: inherit;
}

/* --- レアリティ別枠エフェクト --- */
.card-ur {
    border: 3px solid #ffd700 !important;
    animation: goldGlow 2s infinite alternate;
}

@keyframes goldGlow {
    0% {
        box-shadow: 0 0 15px rgba(255, 215, 0, 0.6), inset 0 0 10px rgba(255, 215, 0, 0.4);
        border-color: #ffd700;
    }
    100% {
        box-shadow: 0 0 35px rgba(255, 215, 0, 1), inset 0 0 25px rgba(255, 215, 0, 0.7);
        border-color: #ffffff;
    }
}

.card-ssr {
    border: 3px solid #c084fc !important;
    box-shadow: 0 0 20px rgba(192, 132, 252, 0.6);
}

.card-sr {
    border: 3px solid #f97316 !important;
    box-shadow: 0 0 15px rgba(249, 115, 22, 0.5);
}

.card-r {
    border: 2px solid #3b82f6 !important;
}

/* --- レアリティバッジ --- */
.rarity-badge {
    display: inline-block;
    padding: 4px 14px;
    border-radius: 20px;
    font-weight: 900;
    font-size: 14px;
    margin-bottom: 8px;
}
.badge-ur { background: linear-gradient(45deg, #ffd700, #ff8c00) !important; color: #000000 !important; box-shadow: 0 0 10px #ffd700; }
.badge-ssr { background: linear-gradient(45deg, #a855f7, #ec4899) !important; color: #ffffff !important; }
.badge-sr { background: linear-gradient(45deg, #f97316, #eab308) !important; color: #ffffff !important; }
.badge-r { background: #3b82f6 !important; color: #ffffff !important; }

/* --- 召喚（ガチャ）ポータル演出 --- */
.summon-portal {
    text-align: center;
    padding: 50px 20px;
    background: radial-gradient(circle, rgba(147,51,234,0.3) 0%, rgba(15,23,42,0.9) 70%);
    border-radius: 20px;
    border: 2px dashed #a855f7;
    animation: portalPulse 1.2s infinite alternate;
    margin-bottom: 20px;
}

@keyframes portalPulse {
    from { opacity: 0.6; transform: scale(0.98); }
    to { opacity: 1.0; transform: scale(1.02); }
}

.monster-title {
    font-size: 26px;
    font-weight: 900;
    margin-bottom: 8px;
    text-shadow: 0 0 10px rgba(0,0,0,0.8);
}

.power-badge {
    background: linear-gradient(135deg, #ff0055, #ff5000) !important;
    color: #ffffff !important;
    font-weight: 900;
    font-size: 20px;
    padding: 6px 18px;
    border-radius: 30px;
    display: inline-block;
    box-shadow: 0 0 15px rgba(255, 0, 85, 0.6);
    margin-top: 10px;
}

.formula-tag {
    font-size: 13px;
    background: rgba(0, 0, 0, 0.6) !important;
    color: #ffffff !important;
    padding: 4px 12px;
    border-radius: 12px;
    display: inline-block;
    margin-bottom: 10px;
}

.element-badge {
    color: #ffffff !important;
    font-weight: 800;
    padding: 4px 14px;
    border-radius: 20px;
    font-size: 13px;
    display: inline-block;
}

.collection-card {
    background: #1a1d2d;
    border: 2px solid #2e344e;
    border-radius: 14px;
    padding: 16px;
    margin-bottom: 16px;
}

.collection-card * {
    color: #ffffff;
}

.stButton > button {
    width: 100%;
    font-weight: 800 !important;
    border-radius: 10px !important;
    padding: 10px 20px !important;
}
</style>
""",
    unsafe_allow_html=True,
)

# ======================================
# サイドバー（錬金設定）
# ======================================
st.sidebar.title("🧪 モンスター作成ラボ")

st.sidebar.subheader("🧬 素材の選択")
material_options = [
    "ドラゴン", "スライム", "ロボット", "寿司", "猫", "サボテン", "ラーメン", "雷雲",
    "魔法使い", "ダイヤモンド", "扇風機", "ゾンビ", "宇宙人", "カレー", "フェニックス",
    "クラーケン", "アイスクリーム", "古代エジプト神", "ブラックホール", "ゲーム機", "天使"
]

material1 = st.sidebar.selectbox("素材 1", material_options, index=0)
material2 = st.sidebar.selectbox("素材 2", material_options, index=3)

custom_word = st.sidebar.text_input("✨ 隠し味（言葉で戦闘力バフ！）", "超覚醒した！！")

st.sidebar.subheader("⚡ 属性")
element = st.sidebar.select_slider(
    "付与属性",
    options=["火", "水", "草", "雷", "サイバー", "闇", "光"],
    value="サイバー",
)

st.sidebar.subheader("🎨 カスタムカラー＆デザイン")
card_bg = st.sidebar.color_picker("カード背景色", "#1e1b2e")
accent_color = st.sidebar.color_picker("メインオーラ色", "#00f2fe")
badge_bg = st.sidebar.color_picker("バッジ色", "#ff007f")
font_style = st.sidebar.selectbox("フォントスタイル", ["sans-serif", "serif", "monospace"], index=0)

# ======================================
# メイン画面
# ======================================
st.title("🧪 AIモンスター ⚔️")

tab1, tab2, tab3 = st.tabs(["🔮 モンスター創造", "📖 自分だけのモンスター図鑑", "⚔️ AIアリーナ（バトル）"])

# --- ステータス & 戦闘力計算 ---
seed_value = sum([ord(c) for c in (material1 + material2 + element + custom_word)])
random.seed(seed_value)

atk = random.randint(40, 99)
dfn = random.randint(40, 99)
spd = random.randint(40, 99)
int_stat = random.randint(40, 99)
hp = random.randint(1000, 9999)

stats_dict = {"HP": hp, "攻撃": atk, "耐久": dfn, "素早さ": spd, "賢さ": int_stat}
power_score, power_breakdown = calculate_power(stats_dict, element, material1, material2, custom_word)

# レアリティ判定の実行
rarity, rarity_badge_class, rarity_card_class = calculate_rarity(power_score, custom_word, material1, material2)

monster_name = f"{custom_word}{material1}{material2}"
special_move = f"超奥義・{material1}式{material2}バースト"
description = f"「{material1}」と「{material2}」の特性を併せ持つ個体。『{custom_word}』の言霊効果により戦闘力が爆発的に向上している。"
weakness = f"{material1}が苦手とする状況、および甘いものの誘惑"

# 保存用モンスターオブジェクト
current_monster = {
    "name": monster_name,
    "formula": f"{material1} × {material2}",
    "word": custom_word,
    "element": element,
    "rarity": rarity,
    "rarity_badge": rarity_badge_class,
    "rarity_card": rarity_card_class,
    "description": description,
    "move": special_move,
    "weakness": weakness,
    "stats": stats_dict,
    "power": power_score,
    "power_breakdown": power_breakdown,
    "design": {
        "bg": card_bg,
        "accent": accent_color,
        "badge": badge_bg,
        "font": font_style
    }
}

status_df = pd.DataFrame({
    "ステータス": ["攻撃力", "耐久力", "素早さ", "賢さ"],
    "値": [atk, dfn, spd, int_stat]
})

# ======================================
# TAB 1: モンスター創造（一体化：召喚 ＋ 自動保存）
# ======================================
with tab1:
    if st.button("🔮 モンスターを召喚して図鑑に保存！", type="primary"):
        portal_placeholder = st.empty()

        # 演出メッセージのステップ（世界観に合わせて3段階で変化）
        summon_steps = [
            (f"⚗️ 元素錬成陣を展開中...", f"『{material1}』と『{material2}』の物質データを抽出中"),
            (f"⚡ 言霊の触媒（『{custom_word}』）を注入中...", f"{element}属性のエレメントと共鳴させています"),
            (f"🧬 新種モンスターの遺伝子結合完了！", f"生命の輝きがカードに定着します...")
        ]

        for title, subtext in summon_steps:
            portal_placeholder.markdown(
                f"""
                <div class="summon-portal">
                    <h2 style="color: #ffffff;">{title}</h2>
                    <p style="color: #e6e6e6;">{subtext}</p>
                </div>
                """,
                unsafe_allow_html=True
            )
            time.sleep(0.5)

        portal_placeholder.empty()

        if not any(m["name"] == monster_name for m in st.session_state["collection"]):
            st.session_state["collection"].append(current_monster)
            st.success(f"🎉 『{monster_name}』(レアリティ: {rarity}) を創造し、図鑑に保存しました！")
        else:
            st.info(f"ℹ️ 『{monster_name}』はすでに図鑑に登録されています。")

        if rarity == "UR":
            st.balloons()

    st.markdown("---")
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("🃏 錬金モンスターカード")

        # カード描画
        st.markdown(
            f"""
        <div class="monster-card {rarity_card_class}" style="background: {card_bg}; border-color: {accent_color}; box-shadow: 0 0 25px {hex_to_rgba(accent_color, 0.4)}; font-family: {font_style};">
            <span class="rarity-badge {rarity_badge_class}">{rarity}</span><br>
            <div class="formula-tag">🧪 {material1} × {material2} (隠し味: {custom_word})</div>
            <div class="monster-title" style="color: {accent_color};">{monster_name}</div>
            <div style="margin-bottom: 8px;">
                属性: <span class="element-badge" style="background: {badge_bg};">{element}</span>
            </div>
            <div class="power-badge">⚔️ 戦闘力: {power_score:,}</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

        st.markdown("#### 📊 ステータス解析")
        fig_radar = px.line_polar(status_df, r="値", theta="ステータス", line_close=True, range_r=[0, 100])
        fig_radar.update_traces(fill="toself", fillcolor=hex_to_rgba(accent_color, 0.35), line_color=accent_color)
        fig_radar.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, range=[0, 100], tickfont=dict(color="#e6e6e6")),
                angularaxis=dict(tickfont=dict(color="#e6e6e6")),
                bgcolor="rgba(0,0,0,0)"
            ),
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e6e6e6"),
            height=230,
            margin=dict(l=30, r=30, t=20, b=20)
        )
        st.plotly_chart(fig_radar, use_container_width=True)

    with col2:
        st.subheader("💥 戦闘力内訳 ＆ 詳細")

        st.json({
            "レアリティ": rarity,
            "合計戦闘力": f"{power_score:,}",
            "ステータス基礎点": power_breakdown["基礎"],
            "言葉文字数ボーナス": f"+{power_breakdown['言葉加算']}",
            "言葉構成乗算(漢字/記号)": power_breakdown["言葉倍率"],
            "属性/素材シナジー乗算": power_breakdown["属性倍率"],
        })

        st.markdown(f"**【図鑑説明】**\n\n{description}")
        st.markdown(f"**【必殺技】**\n\n💥 **{special_move}**")

# ======================================
# TAB 2: モンスター図鑑
# ======================================
with tab2:
    st.subheader(f"📖 マイ・モンスター図鑑 (登録数: {len(st.session_state['collection'])}体)")

    if not st.session_state["collection"]:
        st.info("まだ図鑑にモンスターがいません。Tab 1 で「召喚して図鑑に保存」を押してください！")
    else:
        cols = st.columns(2)
        for idx, item in enumerate(st.session_state["collection"]):
            col = cols[idx % 2]
            d = item["design"]
            with col:
                st.markdown(
                    f"""
                <div class="collection-card {item.get('rarity_card', '')}" style="background: {d['bg']}; font-family: {d['font']};">
                    <span class="rarity-badge {item.get('rarity_badge', 'badge-r')}" style="font-size: 11px;">{item.get('rarity', 'R')}</span>
                    <div style="font-size: 11px; color: #aaa;">{item['formula']}</div>
                    <div style="font-size: 18px; font-weight: 800; color: {d['accent']};">{item['name']}</div>
                    <div style="margin: 6px 0;">
                        <span class="element-badge" style="background: {d['badge']}; font-size: 11px;">{item['element']}</span>
                        <span style="font-size: 14px; font-weight: 900; color: #ff0055; margin-left: 8px;">⚔️ {item['power']:,}</span>
                    </div>
                    <div style="font-size: 12px; color: #ddd;">
                        HP:{item['stats']['HP']} | 攻:{item['stats']['攻撃']} | 防:{item['stats']['耐久']} | 速:{item['stats']['素早さ']}
                    </div>
                </div>
                """,
                    unsafe_allow_html=True,
                )
                with st.expander("詳細＆戦闘力解析"):
                    st.write(item["description"])
                    st.write(f"必殺技: {item['move']}")
                    st.caption(f"言霊倍率: {item['power_breakdown']['言葉倍率']} | 属性倍率: {item['power_breakdown']['属性倍率']}")

# ======================================
# TAB 3: AIアリーナ
# ======================================
with tab3:
    st.subheader("⚔️ AI実況モンスターバトル")
    st.caption("※ APIキーを使用して、戦闘力差や属性相性を加味した熱いバトルを実況します。")

    if len(st.session_state["collection"]) < 1:
        st.warning("⚠️ バトルを行うには、まず図鑑に1体以上のモンスターを保存してください！")
    else:
        col_b1, col_b2 = st.columns(2)

        with col_b1:
            st.markdown("### 🔵 プレイヤー1")
            m1_name = st.selectbox("図鑑から選択 (P1)", [m["name"] for m in st.session_state["collection"]], index=0)
            m1 = next(m for m in st.session_state["collection"] if m["name"] == m1_name)

        with col_b2:
            st.markdown("### 🔴 プレイヤー2")
            options_p2 = ["【野生】伝説のギガ・メカシャーク"] + [m["name"] for m in st.session_state["collection"]]
            m2_name = st.selectbox("対戦相手を選択 (P2)", options_p2, index=0)

            if m2_name == "【野生】伝説のギガ・メカシャーク":
                m2 = {
                    "name": "伝説のギガ・メカシャーク",
                    "element": "水・サイバー",
                    "rarity": "UR",
                    "description": "巨大なロケットパンチを装備した海底の覇者。",
                    "move": "ギガ・メガロ・キャノン",
                    "power": 4500,
                    "stats": {"HP": 6000, "攻撃": 88, "耐久": 85, "素早さ": 50, "賢さ": 40}
                }
            else:
                m2 = next(m for m in st.session_state["collection"] if m["name"] == m2_name)

        st.markdown("---")
        if st.button("🔥 AI実況バトル開始！"):
            if not api_key:
                st.error("⚠️ `.streamlit/secrets.toml` に `GEMINI_API_KEY` を設定してください。")
            else:
                with st.spinner("AIアナウンサーが白熱のバトルを実況中..."):
                    try:
                        client = genai.Client(api_key=api_key)

                        prompt_battle = f"""
以下の2体のモンスターによる夢のバトルロイヤルを実況中継し、勝敗を判定してください。
「戦闘力」や「レアリティ」に差がある場合は、高数値・高レアリティ側が有利になりますが、属性相性や必殺技の展開次第で逆転も可能です。

【1体目】
名前: {m1['name']} (レアリティ: {m1.get('rarity', 'R')})
属性: {m1['element']}
戦闘力: {m1['power']}
説明: {m1['description']}
必殺技: {m1['move']}
ステータス: {m1['stats']}

【2体目】
名前: {m2['name']} (レアリティ: {m2.get('rarity', 'R')})
属性: {m2['element']}
戦闘力: {m2['power']}
説明: {m2['description']}
必殺技: {m2['move']}
ステータス: {m2['stats']}

【出力構成】
1. **開会・両者入場**: 戦闘力とレアリティの比較、属性の有利不利の解説
2. **激闘の第1〜2ターン**: 技の応酬、言語力バフやステータスを活かした激戦の実況
3. **決着**: 勝者の発表と、勝利を決定づけた決め手（戦闘力差や相性などの面白おかしい理由）
"""

                        response = client.models.generate_content(
                            model="gemini-flash-latest",
                            contents=prompt_battle,
                        )

                        st.markdown("### 🏟️ バトル実況ログ")
                        st.info(response.text)
                        st.balloons()

                    except Exception as e:
                        st.error(f"バトル実行エラー: {e}")