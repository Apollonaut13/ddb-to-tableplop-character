import requests
import json
import os
import sys
from dataclasses import dataclass, field

DEBUG = False

dnd_skills = {
    'athletics': 'strength',
    'acrobatics': 'dexterity',
    'sleight-of-hand': 'dexterity',
    'stealth': 'dexterity',
    'arcana': 'intelligence',
    'history': 'intelligence',
    'investigation': 'intelligence',
    'nature': 'intelligence',
    'religion': 'intelligence',
    'animal-handling': 'wisdom',
    'insight': 'wisdom',
    'medicine': 'wisdom',
    'perception': 'wisdom',
    'survival': 'wisdom',
    'deception': 'charisma',
    'intimidation': 'charisma',
    'performance': 'charisma',
    'persuasion': 'charisma'
}

dnd_stats = ['strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma']


@dataclass
class Character:
    name: str = ""
    level: int = 0
    classFeatures: object = None
    classNames: str = ""
    armorClass: int = 0
    maxHP: int = 0
    stats: dict = field(default_factory=dict)
    skills: dict = field(default_factory=dict)
    saves: dict = field(default_factory=dict)

    @property
    def stat_modifier(self) -> dict:
        return {key: (value - 10) // 2 for key, value in self.stats.items()}

    def __str__(self):
        attr_string = '\n'.join(f"{attr}: {value}" for attr, value in self.__dict__.items())
        return 'Character Information'.center(41, '-') + '\n' + attr_string + '\n'


def class_features(data) -> dict:
    # grab the class features because some of them affect hit points and AC
    # store as a dict of objects for easy indexing
    class_features = {}
    for char_class in data.get('classes'):
        for feature in char_class.get('classFeatures'):
            class_level = char_class.get('level')
            if class_level >= feature.get('definition').get('requiredLevel'):
                feature_name = feature.get('definition').get('name')
                feature_obj = {
                    "name": feature_name,
                    "class_level": class_level
                }
                class_features[feature_name] = feature_obj
    return class_features

def unarmored_ac_bonus(character):
    unarmored_ac_bonus = 0
    if 'Draconic Resilience' in character.classFeatures:
        unarmored_ac_bonus = 3
    if 'Monk' in character.classNames:
        unarmored_ac_bonus = character.stat_modifier['wisdom']
    if 'Barbarian' in character.classNames:
        unarmored_ac_bonus = character.stat_modifier['constitution']
    return unarmored_ac_bonus


def all_data_from_ddb_URL(characterURL):
    characterID = characterURL.split('/')[-1]
    if 'ddb.ac' in characterURL or not characterID.isnumeric():
        characterID = characterURL.split('/')[-2]
    r = requests.get(f"https://character-service.dndbeyond.com/character/v3/character/{characterID}")
    characterData = json.loads(r.text)

    if characterData['data'].get('name'):
        print(f"Loaded {characterData['data']['name']}'s character data.")
        if DEBUG:
            with open(f"{characterData['data']['name']}.json", 'w') as outputFile:
                json.dump(characterData, outputFile, indent=4)
        return characterData['data']


    print("Character not found. Exiting.")
    exit()


def build_classSubclassLevel_string_from(data):
    classComboString = ""
    for i, eachClass in enumerate(data.get('classes')):
        className = eachClass['definition']['name']
        subclass = None
        try:
            subclass = eachClass.get('subclassDefinition').get('name')
        except AttributeError:
            pass
        if subclass:
            className += f' ({subclass})'
        className += f" {eachClass.get('level')}"
        classComboString += className
        if i < len(data.get('classes')) - 1:
            classComboString += '/'
    return classComboString


def extract_stats_from(data):
    baseStats = [stat['value'] for stat in data.get('stats')]
    bonusStats = [stat['value'] for stat in data.get('bonusStats')]
    overrideStats = [stat['value'] for stat in data.get('overrideStats')]

    for i in range(6):
        if bonusStats[i]:
            baseStats[i] += bonusStats[i]
        if overrideStats[i]:
            baseStats[i] = overrideStats[i]

    return {statName: baseStats[i] for i, statName in enumerate(dnd_stats)}


def calculate_initiative_from(data, stats, classString):
    initiative = stats['dexterity']
    if 'Ranger (Gloom Stalker)' in classString:
        initiative += stats['wisdom']
    if 'Wizard (War)' in classString:
        initiative += stats['intelligence']
    if data['feats'] and "Alert" in {feat['definition']['name'] for feat in data.get('feats')}:
        initiative += 5
    return initiative


def determine_HP(data, character):
    misc_hp_bonus = 0
    if data['race']['fullName'] == 'Hill Dwarf':
        misc_hp_bonus += character.level

    if "Draconic Resilience" in character.classFeatures:
        misc_hp_bonus += character.classFeatures['Draconic Resilience']['class_level']

    if data['feats'] and "Tough" in {feat['definition']['name'] for feat in data.get('feats')}:
        misc_hp_bonus += 2 * character.level

    if data.get("overrideHitPoints"):
        return data['overrideHitPoints']

    base_hit_points = data.get('baseHitPoints')
    if data.get("bonusHitPoints"):
        base_hit_points += data['bonusHitPoints']
    constitution_bonus = character.level * character.stat_modifier['constitution']
    return base_hit_points + constitution_bonus + misc_hp_bonus


def main():
    if len(sys.argv) == 1:
        characterURL = input("Paste the URL for your character below.\n> ")
    else:
        characterURL = sys.argv[1]

    characterData = all_data_from_ddb_URL(characterURL)
    c = Character()

    c.classFeatures = class_features(characterData)
    c.name = characterData.get('name')
    c.level = sum(eachClass.get('level') for eachClass in characterData.get('classes'))
    c.classNames = build_classSubclassLevel_string_from(characterData)
    c.stats = extract_stats_from(characterData)

    misc_ac_bonus = 0
    for race_Class_Background_Item_Feat_Condition, feature in characterData.get('modifiers').items():
        for detail in feature:
            if detail.get('type') == 'proficiency':
                if detail.get('subType') in dnd_skills.keys():
                    c.skills[detail.get('subType')] = 1
                if detail.get('subType').endswith('saving-throws'):
                    c.saves[detail.get('subType').replace('-saving-throws', '')] = 1
            if (
                detail.get('type') == 'expertise'
                and detail.get('subType') in dnd_skills.keys()
            ):
                c.skills[detail.get('subType')] = 2
            if detail.get('type') == 'bonus':
                if detail.get('subType').endswith('score') and not detail.get('subType').startswith('choose'):
                    c.stats[detail.get('subType').split('-')[0]] += detail.get('value')
                if detail.get('subType').endswith('armor-class'):
                    misc_ac_bonus += detail.get('value')
            if detail.get('type') == 'set' and detail.get('subType').endswith('score'):
                c.stats[detail.get('subType').split('-')[0]] = detail.get('value')

    armorEquipped = False
    for item in characterData.get('inventory'):
        if item['equipped'] and item['definition'].get('grantedModifiers'):
            for grant in item['definition'].get('grantedModifiers'):
                if grant['subType'] == 'armor-class':
                    misc_ac_bonus += grant['value']

        if item['equipped'] and item['definition'].get('armorTypeId'):
            c.armorClass += item['definition'].get('armorClass')
            armorName = item['definition'].get('baseArmorName')
            if armorName in {"Padded", "Leather", "Studded Leather"}:
                armorEquipped = True
                c.armorClass += c.stat_modifier['dexterity']
            if armorName in {"Hide", "Chain Shirt", "Scale Mail", "Breastplate", "Half Plate"}:
                armorEquipped = True
                c.armorClass += min(2, c.stat_modifier['dexterity'])
            if armorName in {"Ring Mail", "Chain Mail", "Splint", "Plate"}:
                armorEquipped = True

    #  shield counts as equipped armor for a monk but
    #  this is not implemented properly on DDB,
    #  has not been since 2020
    #  If it ever is:
    #  * check for armorName == "Shield" above
    #  * check for "Monk" in c.classNames
    #  * set armorEquipped to True if character is a monk with a shield.

    # if a shield is equipped, c.armorClass already accounted for it
    if not armorEquipped:
        c.armorClass += 10 + c.stat_modifier['dexterity'] + unarmored_ac_bonus(c)

    c.armorClass += misc_ac_bonus

    initiative = calculate_initiative_from(characterData, c.stat_modifier, c.classNames)
    c.maxHP = determine_HP(characterData, c)

    sheet = {
        "stats": {},
        "info": {},
        "appearances": {},
        "savedMessages": []
    }
    stats = sheet["stats"]
    proficiencyBonus = 2 + (c.level - 1) // 4
    stats["hit-points-maximum"] = {
        "value": c.maxHP,
        "section": "info",
        "type": "number",
        "hidden": True,
        "parent": "hit-points",
        "local": True
    }
    stats["hit-points"] = {
        "value": c.maxHP,
        "section": "info",
        "type": "health",
        "local": True
    }
    stats["hit-points-temporary"] = {
        "value": 0,
        "section": "info",
        "type": "number",
        "local": True,
        "hidden": True,
        "parent": "hit-points"
    }
    stats["armor-class"] = {
        "value": c.armorClass,
        "section": "info",
        "type": "number"
    }
    stats["proficiency"] = {
        "value": proficiencyBonus,
        "expression": "2+floor((level - 1)/4)",
        "section": "info",
        "type": "number"
    }
    stats["initiative"] = {
        "value": initiative,
        "section": "info",
        "type": "number",
        "roll": "!r initiative = 1d20 + initiative"
    }
    for statName in dnd_stats:
        stat_shorthand = statName[:3]
        stats[statName] = {
            "expression": f"floor(({statName}-score - 10) / 2)",
            "type": "ability",
            "value": c.stat_modifier[statName],
            "section": "abilities",
            "roll": f"{statName} check: {{1d20 + {statName}}}"
        }
        stats[f"{statName}-score"] = {
            "parent": statName,
            "value": c.stats[statName],
            "type": "number",
            "hidden": True
        }
        stats[f"{statName}-save"] = {
            "expression": f"{statName} + ({statName}-save-proficiency ? proficiency : 0)",
            "value": 0,
            "type": "saving-throw",
            "section": "saving-throws",
            "roll": f"{stat_shorthand.upper()} save: {{1d20 + {statName}-save}}"
        }
        stats[f"{statName}-save-proficiency"] = {
            "parent": f"{statName}-save",
            "value": statName in c.saves,
            "type": "checkbox",
            "hidden": True
        }
    stats["level"] = {
        "value": c.level,
        "section": "info",
        "type": "number"
    }

    for skillName, relevant_stat in dnd_skills.items():
        skillExpression = f"{relevant_stat} + ({skillName}-expertise ? proficiency*2 : {skillName}-proficiency ? proficiency : 0)"
        stats[skillName] = {
            "expression": skillExpression,
            "value": 0,
            "subtitle": relevant_stat[:3],
            "type": "skill",
            "section": "skills",
            "roll": f"{skillName.capitalize()} check: {{1d20 + {skillName}}}"
        }
        stats[f"{skillName}-proficiency"] = {
            "value": skillName in c.skills,
            "type": "checkbox",
            "hidden": True,
            "parent": skillName
        }
        stats[f"{skillName}-expertise"] = {
            "value": skillName in c.skills and c.skills[skillName] == 2,
            "type": "checkbox",
            "hidden": True,
            "parent": skillName
        }

    sheet["info"] = {
        "description": "<p><strong>Personality traits:</strong> Enter information here </p><p>&nbsp;</p>",
        "notes": "<p><strong>Ideals:</strong> character ideals here</p><p><strong>Bonds:</strong> character bonds here</p><p><strong>Flaws:</strong> Character flaws here</p><p><strong>Backstory:</strong> Fill in backstory here&nbsp;</p>",
        "sections": [
            {
                "name": "combat",
                "position": "left",
                "tab": 1,
                "savedMessages": False
            },
            {
                "name": "at-will",
                "position": "left",
                "tab": 1,
                "savedMessages": False
            },
            {
                "name": "short-rest",
                "position": "left",
                "tab": 1,
                "savedMessages": False
            },
            {
                "name": "once-per-day",
                "position": "left",
                "tab": 1,
                "savedMessages": False
            },
            {
                "name": "combat-messages",
                "position": "bottom",
                "tab": 1,
                "savedMessages": True
            },
            {
                "name": "About-Character-Sheet",
                "position": "bottom",
                "tab": 1,
                "savedMessages": False
            },
            {
                "name": "Feats",
                "position": "bottom",
                "tab": 2,
                "savedMessages": False
            },
            {
                "name": "saving-throws",
                "position": "right",
                "tab": 2
            },
            {
                "name": "senses",
                "position": "right",
                "tab": 2
            },
            {
                "name": "skills",
                "position": "right",
                "tab": 2
            },
            {
                "name": "overview",
                "position": "left",
                "tab": 3,
                "savedMessages": False
            },
            {
                "name": "abilities",
                "position": "bottom",
                "tab": 3
            },
            {
                "name": "info",
                "position": "left",
                "tab": 3
            },
            {
                "name": "details",
                "position": "left",
                "tab": 3
            },
            {
                "name": "char-sheet-internal",
                "position": "bottom",
                "tab": 3,
                "hidden": True,
                "__comment": "Marking a section hidden currently has no effect, but leave it in in case the next rev implements it.",
                "savedMessages": False
            },
            {
                "name": "actions",
                "position": "bottom",
                "tab": 4,
                "savedMessages": True
            },
            {
                "name": "spells",
                "position": "bottom",
                "tab": 4,
                "savedMessages": True
            }
        ]
    }
    sheet['appearances'] = []

    sheet['savedMessages'] = []
    json.dump(sheet, open(f'{c.name.lower().replace(" ", "_")}_tableplop.json', 'w'), indent=4)

    print(c)
    print('Tableplop Character JSON created!')
    print(f'To see the file, open {os.getcwd()}')


if __name__ == "__main__":
    main()
