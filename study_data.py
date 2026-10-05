"""教材清单(OpenStax 开放教材,按顺序学习)。"""

BOOKS = {
    "天文学": {
        "name": "OpenStax Astronomy 2e", "slug": "astronomy-2e",
        "chapters": [
            ("Science and the Universe: A Brief Tour", "科学与宇宙概览"),
            ("Observing the Sky: The Birth of Astronomy", "观测天空:天文学的诞生"),
            ("Orbits and Gravity", "轨道与引力"),
            ("Earth, Moon, and Sky", "地球、月球与天空"),
            ("Radiation and Spectra", "辐射与光谱"),
            ("Astronomical Instruments", "天文仪器"),
            ("Other Worlds: An Introduction to the Solar System", "其他世界:太阳系导论"),
            ("Earth as a Planet", "地球作为行星"),
            ("Cratered Worlds", "布满陨石坑的世界"),
            ("Earthlike Planets: Venus and Mars", "类地行星:金星与火星"),
            ("The Giant Planets", "巨行星"),
            ("Rings, Moons, and Pluto", "行星环、卫星与冥王星"),
            ("Comets and Asteroids: Debris of the Solar System", "彗星与小行星"),
            ("Cosmic Samples and the Origin of the Solar System", "宇宙样本与太阳系起源"),
            ("The Sun: A Garden-Variety Star", "太阳:普通恒星"),
            ("The Sun: A Nuclear Powerhouse", "太阳:核动力工厂"),
            ("Analyzing Starlight", "分析星光"),
            ("The Stars: A Celestial Census", "恒星普查"),
            ("Celestial Distances", "天体距离"),
            ("Between the Stars: Gas and Dust in Space", "星际气体与尘埃"),
            ("The Birth of Stars and the Discovery of Planets outside the Solar System", "恒星诞生与系外行星"),
            ("Stars from Adolescence to Old Age", "恒星从青年到老年"),
            ("The Death of Stars", "恒星之死"),
            ("Black Holes and Curved Spacetime", "黑洞与弯曲时空"),
            ("The Milky Way Galaxy", "银河系"),
            ("Galaxies", "星系"),
            ("Active Galaxies, Quasars, and Supermassive Black Holes", "活动星系、类星体与超大质量黑洞"),
            ("The Evolution and Distribution of Galaxies", "星系的演化与分布"),
            ("The Big Bang", "宇宙大爆炸"),
            ("Life in the Universe", "宇宙中的生命"),
        ],
    },
    "心理学": {
        "name": "OpenStax Psychology 2e", "slug": "psychology-2e",
        "chapters": [
            ("Introduction to Psychology", "心理学导论"),
            ("Psychological Research", "心理学研究方法"),
            ("Biopsychology", "生物心理学"),
            ("States of Consciousness", "意识状态"),
            ("Sensation and Perception", "感觉与知觉"),
            ("Learning", "学习"),
            ("Thinking and Intelligence", "思维与智力"),
            ("Memory", "记忆"),
            ("Lifespan Development", "毕生发展"),
            ("Emotion and Motivation", "情绪与动机"),
            ("Personality", "人格"),
            ("Social Psychology", "社会心理学"),
            ("Industrial-Organizational Psychology", "工业与组织心理学"),
            ("Stress, Lifestyle, and Health", "压力、生活方式与健康"),
            ("Psychological Disorders", "心理障碍"),
            ("Therapy and Treatment", "治疗"),
        ],
    },
}


def chapter_url(book, n):
    return f"https://openstax.org/books/{book['slug']}/pages/{n}-introduction"


# ---------- 长期计划:雅思阶段目标 ----------
# (检查点日期, 目标分数)。当前阶段的目标分数决定每天雅思短文的难度。
# 这是常见节奏的估计,不是保证;每到检查点请做一套完整模考核对真实水平。
IELTS_MILESTONES = [
    ("2027-01-05", 6.0),
    ("2027-04-05", 6.5),
    ("2027-07-05", 7.0),
    ("2027-10-05", 7.5),
]


def ielts_stage(today):
    """返回 (当前阶段目标分数, 检查点日期)。全部过期后停在最终目标。"""
    for by, band in IELTS_MILESTONES:
        if today.isoformat() <= by:
            return band, by
    return IELTS_MILESTONES[-1][1], IELTS_MILESTONES[-1][0]
