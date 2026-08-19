"""
带隐藏机制的文字寻宝游戏。
灵感来自 Shunyu Yao 关于 AI 推理与泛化的观点。
"""

import random
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, field
from enum import Enum


class ItemType(Enum):
    KEY = "key"
    WEAPON = "weapon"
    TREASURE = "treasure"
    TOOL = "tool"
    POTION = "potion"


@dataclass
class Item:
    name: str
    item_type: ItemType
    description: str
    properties: Dict[str, any] = field(default_factory=dict)


@dataclass
class Room:
    name: str
    description: str
    items: List[Item] = field(default_factory=list)
    exits: Dict[str, str] = field(default_factory=dict)  # direction -> room_name
    locked_exits: Dict[str, str] = field(default_factory=dict)  # direction -> required_key
    has_guard: bool = False
    guard_defeated: bool = False


class TreasureHuntGame:
    """
    一个带隐藏机制的文字游戏，智能体必须自行发现这些机制：
    1. 特定颜色的钥匙打开对应颜色的门
    2. 守卫挡住通往宝藏的路，需要特定武器才能击败
    3. 某些物品可以组合成新物品（隐藏的合成机制）
    4. 药水提供临时能力
    """

    def __init__(self, seed: int = None, stochastic: bool = False):
        """
        初始化游戏环境。

        Args:
            seed: 随机种子，用于复现
            stochastic: 若为 True，则向游戏加入随机要素
        """
        # NOTE: 不要在这里调用 random.seed()。reset() 每局都会用一个全新的
        # 14 位种子重新执行 __init__，而学习型智能体的探索动作取自
        # *全局* random 模块——在这里重置种子会把该随机流每局钉死在
        # 仅有的 10001 个状态之一上，导致整局过程逐字重复。环境自身的
        # 随机性独立封装在下面的 self.random_state 里，它仍由 `seed` 播种。
        self.stochastic = stochastic
        self.random_state = random.Random(seed) if stochastic else None
        
        self.rooms = {}
        self.current_room = None
        self.inventory = []
        self.score = 0
        self.moves = 0
        self.max_moves = 50  # 已调低以加快每局节奏
        self.game_over = False
        self.victory = False
        self.active_effects = {}

        # 隐藏机制（初始不向智能体透露）
        self.color_key_mapping = {
            "red key": "red door",
            "blue key": "blue door",
            "golden key": "golden door"
        }
        
        self.weapon_effectiveness = {
            "rusty sword": ["weak guard"],
            "silver sword": ["weak guard", "strong guard", "dragon"]
        }
        
        self.crafting_recipes = {
            frozenset(["rusty sword", "magic crystal"]): "silver sword"
        }
        
        self._initialize_world()
    
    def _initialize_world(self):
        """创建包含房间与物品的游戏世界——已简化以便于学习。"""

        # 构建一个更易学习、但仍能演示相关概念的简化世界
        self.rooms["entrance"] = Room(
            name="entrance",
            description="You stand in a dimly lit entrance hall. Stone walls echo your footsteps.",
            items=[
                Item("rusty sword", ItemType.WEAPON, "An old sword with rust spots")
            ],
            exits={"north": "hallway", "east": "storage"}
        )
        
        self.rooms["storage"] = Room(
            name="storage",
            description="A dusty storage room filled with old crates and barrels.",
            items=[
                Item("red key", ItemType.KEY, "A small red metal key"),
                Item("magic crystal", ItemType.TOOL, "A glowing crystal that hums with energy")
            ],
            exits={"west": "entrance"}
        )
        
        self.rooms["hallway"] = Room(
            name="hallway",
            description="A long hallway with a locked door to the north.",
            exits={"south": "entrance", "north": "guard_room"},
            locked_exits={"north": "red key"}
        )
        
        self.rooms["guard_room"] = Room(
            name="guard_room",
            description="A large room with weapon racks. A guard blocks the treasure!",
            has_guard=True,
            items=[],
            exits={"south": "hallway", "east": "treasure_room"}
        )
        
        self.rooms["treasure_room"] = Room(
            name="treasure_room",
            description="The treasure room! Gold coins and jewels sparkle in the light.",
            items=[
                Item("dragon's treasure", ItemType.TREASURE, "A massive hoard of gold and gems", 
                     {"value": 1000})
            ],
            exits={"west": "guard_room"}
        )
        
        self.current_room = self.rooms["entrance"]
    
    def get_state_description(self) -> str:
        """返回当前游戏状态的自然语言描述。"""
        desc = []
        desc.append(f"\n=== Room: {self.current_room.name.replace('_', ' ').title()} ===")
        desc.append(self.current_room.description)
        
        if self.current_room.has_guard and not self.current_room.guard_defeated:
            desc.append("A guard blocks your way!")
        
        if self.current_room.items:
            desc.append("\nYou see:")
            for item in self.current_room.items:
                desc.append(f"  - {item.name}: {item.description}")
        
        exits = []
        for direction, room in self.current_room.exits.items():
            if direction in self.current_room.locked_exits:
                exits.append(f"{direction} (locked)")
            else:
                exits.append(direction)
        desc.append(f"\nExits: {', '.join(exits)}")
        
        if self.inventory:
            desc.append(f"\nInventory: {', '.join([item.name for item in self.inventory])}")
        
        desc.append(f"\nScore: {self.score} | Moves: {self.moves}/{self.max_moves}")
        
        return "\n".join(desc)
    
    def get_available_actions(self) -> List[str]:
        """返回当前状态下可用的动作列表。"""
        actions = []

        # 移动动作
        for direction in self.current_room.exits.keys():
            actions.append(f"go {direction}")

        # 物品动作
        for item in self.current_room.items:
            actions.append(f"take {item.name}")
        
        for item in self.inventory:
            actions.append(f"use {item.name}")
            actions.append(f"drop {item.name}")
        
        # 战斗动作
        if self.current_room.has_guard and not self.current_room.guard_defeated:
            for item in self.inventory:
                if item.item_type == ItemType.WEAPON:
                    actions.append(f"attack with {item.name}")

        # 特殊动作
        actions.append("look around")
        actions.append("check inventory")

        # 合成（玩家发现该机制后可尝试）
        if len(self.inventory) >= 2:
            actions.append("try crafting")
        
        return actions
    
    def execute_action(self, action: str) -> Tuple[str, float, bool]:
        """
        执行一个动作，返回 (feedback, reward, done)。
        """
        if self.game_over:
            return "Game is already over.", 0, True

        self.moves += 1
        action = action.lower().strip()
        # 第 N 步仍须执行，因此步数上限在动作分发之后再强制检查
        # （失误提前返回的分支同样要检查——此前该分支绕过了上限，
        # 一局可以超出步数封顶继续进行）。
        out_of_moves = self.moves >= self.max_moves

        # 基础奖励，随机模式下带扰动
        if self.stochastic:
            # 给奖励加小幅随机扰动
            reward = -0.5 + self.random_state.uniform(-0.1, 0.1)

            # 随机模式下动作有小概率失误
            if self.random_state.random() < 0.03:  # 3% 概率
                if out_of_moves:
                    self.game_over = True
                    return ("You fumble — and you've run out of moves! Game over.",
                            reward - 10, True)
                return "You fumble and need to try again.", reward - 0.2, False
        else:
            reward = -0.5  # 每步给负奖励，鼓励高效行动

        # 解析动作
        if action.startswith("go "):
            direction = action[3:]
            result, move_reward = self._move(direction)
            reward += move_reward
            
        elif action.startswith("take "):
            item_name = action[5:]
            result, take_reward = self._take_item(item_name)
            reward += take_reward
            
        elif action.startswith("use "):
            item_name = action[4:]
            result, use_reward = self._use_item(item_name)
            reward += use_reward
            
        elif action.startswith("drop "):
            item_name = action[5:]
            result = self._drop_item(item_name)
            
        elif action.startswith("attack with "):
            weapon_name = action[12:]
            result, attack_reward = self._attack(weapon_name)
            reward += attack_reward
            
        elif action == "look around":
            result = self.get_state_description()
            
        elif action == "check inventory":
            if self.inventory:
                result = "Inventory: " + ", ".join([f"{item.name} ({item.item_type.value})" 
                                                    for item in self.inventory])
            else:
                result = "Your inventory is empty."
                
        elif action == "try crafting":
            result, craft_reward = self._try_crafting()
            reward += craft_reward
            
        else:
            result = f"Unknown action: {action}"
            reward -= 1
        
        # 检查胜利条件
        if self._check_victory():
            self.victory = True
            self.game_over = True
            reward += 100
            result += "\n\n🎉 VICTORY! You've collected the dragon's treasure!"

        # 动作执行完毕后再强制步数上限：在最后一步打出制胜动作仍算胜利。
        if not self.game_over and out_of_moves:
            self.game_over = True
            reward -= 10
            result += "\n\nYou've run out of moves! Game over."

        return result, reward, self.game_over
    
    def _move(self, direction: str) -> Tuple[str, float]:
        """移动到另一个房间。"""
        if direction not in self.current_room.exits:
            return f"You can't go {direction} from here.", -1

        # 检查是否上锁
        if direction in self.current_room.locked_exits:
            required_key = self.current_room.locked_exits[direction]
            if not any(item.name == required_key for item in self.inventory):
                return f"The {direction} exit is locked. You need a {required_key}.", -0.5
            else:
                # 解锁并移动
                del self.current_room.locked_exits[direction]
                room_name = self.current_room.exits[direction]
                self.current_room = self.rooms[room_name]
                return f"You unlock the door with the {required_key} and move {direction}.", 5

        # 检查守卫
        if self.current_room.has_guard and not self.current_room.guard_defeated:
            return "A guard blocks your way! You must defeat them first.", -1

        # 移动到新房间
        room_name = self.current_room.exits[direction]
        self.current_room = self.rooms[room_name]
        return f"You move {direction} to the {self.current_room.name}.", 1
    
    def _take_item(self, item_name: str) -> Tuple[str, float]:
        """拾取物品。"""
        for item in self.current_room.items:
            if item.name.lower() == item_name.lower():
                self.current_room.items.remove(item)
                self.inventory.append(item)

                # 按物品类型给奖励
                if item.item_type == ItemType.TREASURE:
                    reward = 100  # 拿到宝藏给大奖励！
                elif item.item_type == ItemType.KEY:
                    reward = 5
                elif item.item_type == ItemType.WEAPON:
                    reward = 3
                else:
                    reward = 2

                # 加随机扰动
                if self.stochastic:
                    reward += self.random_state.uniform(-0.5, 0.5)
                    
                return f"You take the {item.name}.", reward
        
        penalty = -0.5
        if self.stochastic:
            penalty += self.random_state.uniform(-0.1, 0.1)
        
        return f"There's no {item_name} here.", penalty
    
    def _drop_item(self, item_name: str) -> str:
        """丢弃物品。"""
        for item in self.inventory:
            if item.name.lower() == item_name.lower():
                self.inventory.remove(item)
                self.current_room.items.append(item)
                return f"You drop the {item.name}."
        
        return f"You don't have a {item_name}."
    
    def _use_item(self, item_name: str) -> Tuple[str, float]:
        """使用物品。"""
        for item in self.inventory:
            if item.name.lower() == item_name.lower():
                if item.item_type == ItemType.POTION:
                    self.inventory.remove(item)
                    if "healing" in item.name:
                        return "You drink the healing potion and feel refreshed!", 5
                    elif "strength" in item.name:
                        self.active_effects["strength"] = 10
                        return "You feel a surge of power! Your attacks will be stronger.", 5
                    
                elif item.item_type == ItemType.KEY:
                    # 钥匙在移动时自动使用
                    return f"The {item.name} will be used automatically when needed.", 0
                    
                else:
                    return f"You can't use the {item.name} right now.", -0.5
        
        return f"You don't have a {item_name}.", -0.5
    
    def _attack(self, weapon_name: str) -> Tuple[str, float]:
        """用武器攻击。"""
        if not self.current_room.has_guard or self.current_room.guard_defeated:
            return "There's nothing to attack here.", -1
        
        weapon = None
        for item in self.inventory:
            if item.name.lower() == weapon_name.lower():
                weapon = item
                break
        
        if not weapon:
            return f"You don't have a {weapon_name}.", -1
        
        if weapon.item_type != ItemType.WEAPON:
            return f"The {weapon_name} is not a weapon!", -1
        
        # 检查武器克制关系（隐藏机制）
        # 在简化版游戏里，guard_room 中的守卫是 "strong guard"
        guard_type = "strong guard"

        if weapon.name in self.weapon_effectiveness:
            if guard_type in self.weapon_effectiveness[weapon.name]:
                # 随机模式下加入战斗变化
                if self.stochastic:
                    roll = self.random_state.random()
                    if roll < 0.1:  # 10% 概率暴击
                        self.current_room.guard_defeated = True
                        return f"Critical hit! You defeat the {guard_type} with your {weapon.name}!", 30
                    elif roll < 0.95:  # 85% 概率普通命中
                        self.current_room.guard_defeated = True
                        return f"You defeat the {guard_type} with your {weapon.name}!", 20
                    else:  # 5% 概率攻击擦过
                        return f"Your attack glances off! The {guard_type} is still standing.", -0.5
                else:
                    self.current_room.guard_defeated = True
                    return f"You defeat the {guard_type} with your {weapon.name}!", 20
            else:
                penalty = -2
                if self.stochastic:
                    penalty += self.random_state.uniform(-0.5, 0.5)
                return f"Your {weapon.name} is not effective against the {guard_type}!", penalty
        
        return f"Your {weapon.name} doesn't seem to work.", -1
    
    def _try_crafting(self) -> Tuple[str, float]:
        """尝试合成物品（隐藏机制）。"""
        if len(self.inventory) < 2:
            return "You need at least two items to craft.", -0.5

        # 检查所有可能的组合
        inventory_names = [item.name for item in self.inventory]

        for recipe, result in self.crafting_recipes.items():
            if recipe.issubset(set(inventory_names)):
                # 随机模式下合成可能有变化
                if self.stochastic:
                    if self.random_state.random() < 0.9:  # 90% 成功率
                        # 合成物品
                        for ingredient in recipe:
                            for item in self.inventory[:]:
                                if item.name == ingredient:
                                    self.inventory.remove(item)
                                    break
                        
                        new_item = self._create_item(result)
                        self.inventory.append(new_item)
                        reward = 10 + self.random_state.uniform(-1, 2)
                        return f"You successfully craft a {result}!", reward
                    else:
                        # 10% 概率合成失手（材料不消耗）
                        return "The crafting attempt fizzles. Try again!", -0.2
                else:
                    # 确定性合成
                    for ingredient in recipe:
                        for item in self.inventory[:]:
                            if item.name == ingredient:
                                self.inventory.remove(item)
                                break
                    
                    new_item = self._create_item(result)
                    self.inventory.append(new_item)
                    return f"You successfully craft a {result}!", 10  # 发现合成机制给不错的奖励
        
        penalty = -0.5
        if self.stochastic:
            penalty += self.random_state.uniform(-0.1, 0.1)
        
        return "These items don't combine into anything useful.", penalty
    
    def _create_item(self, item_name: str) -> Item:
        """按名称创建物品。"""
        if item_name == "silver sword":
            return Item("silver sword", ItemType.WEAPON, "A gleaming silver blade")
        elif item_name == "magic staff":
            return Item("magic staff", ItemType.WEAPON, "A staff crackling with magical energy")
        else:
            return Item(item_name, ItemType.TOOL, "A crafted item")
    
    def _check_victory(self) -> bool:
        """检查玩家是否获胜。"""
        for item in self.inventory:
            if item.name == "dragon's treasure":
                return True
        return False
    
    def reset(self, seed: int = None) -> str:
        """将游戏重置到初始状态。"""
        if seed is None:
            seed = random.randint(0, 10000)
        self.__init__(seed=seed, stochastic=self.stochastic)
        return self.get_state_description()
    
    def get_hidden_rules(self) -> str:
        """返回隐藏的游戏规则（供调试/分析用）。"""
        rules = []
        rules.append("Hidden Game Mechanics (Simplified Version):")
        rules.append("\n1. To win the game:")
        rules.append("   - Get the red key from storage room")
        rules.append("   - Use it to unlock the door to guard room")
        rules.append("   - Craft a silver sword (rusty sword + magic crystal)")
        rules.append("   - Defeat the strong guard with the silver sword")
        rules.append("   - Collect the dragon's treasure")
        
        rules.append("\n2. Key mechanics:")
        rules.append("   - Red key opens the locked door in the hallway")
        
        rules.append("\n3. Weapon effectiveness:")
        for weapon, targets in self.weapon_effectiveness.items():
            rules.append(f"   - {weapon} defeats: {', '.join(targets)}")
        
        rules.append("\n4. Crafting recipe:")
        for ingredients, result in self.crafting_recipes.items():
            rules.append(f"   - {' + '.join(ingredients)} = {result}")
        
        rules.append("\n5. Optimal solution:")
        rules.append("   - Takes about 10-15 moves if done efficiently")
        
        return "\n".join(rules)
