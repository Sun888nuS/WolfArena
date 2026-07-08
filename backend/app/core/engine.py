"""确定性狼人杀规则引擎。

本模块是唯一可以修改 `GameState` 真相状态的规则层入口。LangGraph 和 LLM
Agent 只能调用这里暴露的方法，不能绕过规则引擎直接改生死、阶段或胜负。
"""

from app.core.events import append_event
from app.core.exceptions import InvalidActionError
from app.core.models import (
    Alignment,
    DeathReason,
    EventType,
    EventVisibility,
    GameState,
    NightActionBuffer,
    Phase,
    Role,
    VoteRecord,
    VoteResult,
    Winner,
)
from app.core.rules import (
    alive_players,
    alive_werewolves,
    check_winner,
    create_standard_12_player_game_players,
    find_role_player,
    get_player,
    legal_hunter_shot_targets,
    legal_sheriff_vote_targets,
    require_phase,
    resolve_vote_records,
    validate_seer_check,
    validate_vote,
    validate_werewolf_kill,
    validate_witch_action,
    voting_players,
)


DEFAULT_PLAYER_NAMES: list[str] = [
    "玩家a",
    "玩家b",
    "玩家c",
    "玩家d",
    "玩家e",
    "玩家f",
    "玩家g",
    "玩家h",
    "玩家i",
    "玩家j",
    "玩家k",
    "玩家l",
]


class WerewolfEngine:
    """单局狼人杀的有状态规则引擎。"""

    def __init__(
        self,
        player_names: list[str] | None = None,
        *,
        human_player_id: str | None = "p1",
        seed: int | None = None,
    ) -> None:
        """初始化一局 12 人标准局，分配身份和座位，并写入开局事件。"""
        names = player_names or DEFAULT_PLAYER_NAMES
        players = create_standard_12_player_game_players(
            names,
            human_player_id=human_player_id,
            seed=seed,
        )
        self.state = GameState(players=players)
        append_event(
            self.state,
            EventType.GAME_CREATED,
            visibility=EventVisibility.PUBLIC,
            payload={"player_count": len(players), "ruleset": "standard_12"},
        )
        for player in players:
            append_event(
                self.state,
                EventType.ROLE_ASSIGNED,
                visibility=EventVisibility.PRIVATE,
                actor_id=player.player_id,
                recipients=(player.player_id,),
                payload={"role": player.role.value, "alignment": player.alignment.value},
            )
        append_event(
            self.state,
            EventType.NIGHT_STARTED,
            visibility=EventVisibility.PUBLIC,
            payload={"round": self.state.round_no},
        )

    def select_werewolf_kill(self, actor_id: str, target_id: str) -> None:
        """记录狼队最终统一的夜晚袭击目标。"""
        require_phase(self.state, Phase.NIGHT)
        validate_werewolf_kill(self.state, actor_id=actor_id, target_id=target_id)
        living_wolves = sorted(player.player_id for player in alive_werewolves(self.state))
        if actor_id not in living_wolves:
            raise InvalidActionError("只有存活狼人可以选择袭击目标。")
        self.state.night_actions.werewolf_actor_id = actor_id
        self.state.night_actions.werewolf_target_id = target_id
        self.state.night_actions.werewolf_intents = {
            wolf_id: target_id for wolf_id in living_wolves
        }
        append_event(
            self.state,
            EventType.WEREWOLF_KILL_SELECTED,
            visibility=EventVisibility.WEREWOLVES,
            actor_id=actor_id,
            payload={"target_id": target_id},
        )

    def record_werewolf_kill_intent(self, actor_id: str, target_id: str) -> str | None:
        """记录单个狼人刀人意向；全部一致时返回统一目标。"""
        require_phase(self.state, Phase.NIGHT)
        validate_werewolf_kill(self.state, actor_id=actor_id, target_id=target_id)
        buffer = self.state.night_actions
        if buffer.werewolf_target_id is not None:
            raise InvalidActionError("狼队袭击目标已经确定。")

        living_wolves = sorted(player.player_id for player in alive_werewolves(self.state))
        if actor_id not in living_wolves:
            raise InvalidActionError("只有存活狼人可以提交刀人意向。")
        if buffer.werewolf_intent_round < 1:
            buffer.werewolf_intent_round = 1
        buffer.werewolf_intents[actor_id] = target_id
        append_event(
            self.state,
            EventType.WEREWOLF_KILL_INTENT_RECORDED,
            visibility=EventVisibility.WEREWOLVES,
            actor_id=actor_id,
            payload={
                "target_id": target_id,
                "intent_round": buffer.werewolf_intent_round,
            },
        )

        if not all(wolf_id in buffer.werewolf_intents for wolf_id in living_wolves):
            return None
        targets = {buffer.werewolf_intents[wolf_id] for wolf_id in living_wolves}
        if len(targets) == 1:
            consensus_target = targets.pop()
            self.state.night_actions.werewolf_actor_id = actor_id
            self.state.night_actions.werewolf_target_id = consensus_target
            append_event(
                self.state,
                EventType.WEREWOLF_KILL_SELECTED,
                visibility=EventVisibility.WEREWOLVES,
                actor_id=actor_id,
                payload={"target_id": consensus_target},
            )
            return consensus_target

        append_event(
            self.state,
            EventType.WEREWOLF_CONSENSUS_REQUIRED,
            visibility=EventVisibility.WEREWOLVES,
            payload={
                "intent_round": buffer.werewolf_intent_round,
                "intents": dict(buffer.werewolf_intents),
            },
        )
        buffer.werewolf_intent_round += 1
        buffer.werewolf_intents.clear()
        return None

    def seer_check(self, actor_id: str, target_id: str) -> Alignment:
        """记录预言家查验行动，并返回目标阵营。"""
        require_phase(self.state, Phase.NIGHT)
        validate_seer_check(self.state, actor_id=actor_id, target_id=target_id)
        target = get_player(self.state, target_id)
        result = target.alignment
        self.state.night_actions.seer_actor_id = actor_id
        self.state.night_actions.seer_target_id = target_id
        self.state.seer_results.setdefault(actor_id, {})[target_id] = result
        append_event(
            self.state,
            EventType.SEER_CHECKED,
            visibility=EventVisibility.PRIVATE,
            actor_id=actor_id,
            recipients=(actor_id,),
            payload={"target_id": target_id, "alignment": result.value},
        )
        return result

    def witch_action(
        self,
        actor_id: str,
        *,
        save: bool = False,
        poison_target_id: str | None = None,
    ) -> None:
        """记录女巫夜晚用药行动。"""
        require_phase(self.state, Phase.NIGHT)
        validate_witch_action(
            self.state,
            actor_id=actor_id,
            save=save,
            poison_target_id=poison_target_id,
        )
        self.state.night_actions.witch_actor_id = actor_id
        self.state.night_actions.witch_save = save
        self.state.night_actions.witch_poison_target_id = poison_target_id
        if save:
            self.state.witch_state.has_antidote = False
        if poison_target_id is not None:
            self.state.witch_state.has_poison = False
        append_event(
            self.state,
            EventType.WITCH_ACTED,
            visibility=EventVisibility.PRIVATE,
            actor_id=actor_id,
            recipients=(actor_id,),
            payload={"save": save, "poison_target_id": poison_target_id},
        )

    def confirm_hunter_status(self, actor_id: str) -> bool:
        """猎人夜晚确认技能状态。"""
        require_phase(self.state, Phase.NIGHT)
        actor = get_player(self.state, actor_id)
        if actor.role is not Role.HUNTER:
            raise InvalidActionError("只有猎人可以确认技能状态。")
        self.state.night_actions.hunter_actor_id = actor_id
        can_shoot = actor.alive and not self.state.hunter_shot_used
        append_event(
            self.state,
            EventType.HUNTER_STATUS_CONFIRMED,
            visibility=EventVisibility.PRIVATE,
            actor_id=actor_id,
            recipients=(actor_id,),
            payload={"can_shoot": can_shoot},
        )
        return can_shoot

    def confirm_idiot(self, actor_id: str) -> None:
        """白痴夜晚确认身份。"""
        require_phase(self.state, Phase.NIGHT)
        actor = get_player(self.state, actor_id)
        if actor.role is not Role.IDIOT:
            raise InvalidActionError("只有白痴可以确认身份。")
        self.state.night_actions.idiot_actor_id = actor_id
        append_event(
            self.state,
            EventType.IDIOT_CONFIRMED,
            visibility=EventVisibility.PRIVATE,
            actor_id=actor_id,
            recipients=(actor_id,),
            payload={"confirmed": True},
        )

    def resolve_night(self) -> tuple[str, ...]:
        """结算夜晚死亡，并进入白天发言或游戏结束。"""
        require_phase(self.state, Phase.NIGHT)

        death_reasons: dict[str, DeathReason] = {}
        killed = self.state.night_actions.werewolf_target_id
        if killed and not self.state.night_actions.witch_save:
            death_reasons[killed] = DeathReason.WEREWOLF_KILL

        poison_target = self.state.night_actions.witch_poison_target_id
        if poison_target is not None:
            death_reasons[poison_target] = DeathReason.WITCH_POISON

        deaths = tuple(sorted(death_reasons, key=lambda player_id: get_player(self.state, player_id).seat))
        for player_id in deaths:
            self._kill_player(player_id, death_reasons[player_id])

        self.state.last_dead_player_ids = deaths
        append_event(
            self.state,
            EventType.NIGHT_RESOLVED,
            visibility=EventVisibility.PUBLIC,
            payload={
                "dead_player_ids": deaths,
                "death_reasons": {
                    player_id: death_reasons[player_id].value for player_id in deaths
                },
            },
        )
        self.state.phase = Phase.DAY_SPEECH
        self._check_and_set_winner()
        return deaths

    def resolve_death_reactions(
        self,
        *,
        hunter_shot_target_id: str | None = None,
        idiot_reveal: bool = True,
        sheriff_handoff_target_id: str | None = None,
    ) -> tuple[str, ...]:
        """结算死亡后的猎人、白痴和警徽移交反应。"""
        extra_deaths: list[str] = []
        trigger_ids = [
            player_id
            for player_id in (*self.state.last_dead_player_ids, self.state.last_exiled_player_id)
            if player_id
        ]
        for player_id in trigger_ids:
            player = get_player(self.state, player_id)
            if (
                player.role is Role.HUNTER
                and not self.state.hunter_shot_used
                and player.dead_reason in {DeathReason.WEREWOLF_KILL, DeathReason.EXILE}
            ):
                if hunter_shot_target_id is not None:
                    if hunter_shot_target_id not in legal_hunter_shot_targets(self.state, player_id):
                        raise InvalidActionError(f"非法猎人开枪目标：{hunter_shot_target_id}")
                    self.state.hunter_shot_used = True
                    self._kill_player(hunter_shot_target_id, DeathReason.HUNTER_SHOT)
                    extra_deaths.append(hunter_shot_target_id)
                    append_event(
                        self.state,
                        EventType.HUNTER_SHOT,
                        visibility=EventVisibility.PUBLIC,
                        actor_id=player_id,
                        payload={"target_id": hunter_shot_target_id},
                    )
                else:
                    self.state.hunter_shot_used = True
                    append_event(
                        self.state,
                        EventType.DEATH_REACTION_RESOLVED,
                        visibility=EventVisibility.PUBLIC,
                        actor_id=player_id,
                        payload={"hunter_shot": False},
                    )

            if (
                player.role is Role.IDIOT
                and player.dead_reason is DeathReason.EXILE
                and not self.state.idiot_revealed
            ):
                if idiot_reveal:
                    player.revealed_role = True
                    player.can_speak_after_death = True
                    player.can_vote = False
                    self.state.idiot_revealed = True
                    append_event(
                        self.state,
                        EventType.IDIOT_REVEALED,
                        visibility=EventVisibility.PUBLIC,
                        actor_id=player_id,
                        payload={"revealed": True},
                    )

            if player_id == self.state.sheriff_id:
                self.handoff_sheriff(sheriff_handoff_target_id)

        if extra_deaths:
            self.state.last_dead_player_ids = tuple(extra_deaths)
        self._check_and_set_winner()
        return tuple(extra_deaths)

    def start_sheriff_election(self) -> None:
        """进入警长竞选阶段。"""
        if self.state.sheriff_election_done or self.state.sheriff_badge_lost:
            return
        self.state.phase = Phase.SHERIFF_ELECTION
        self.state.sheriff_votes.clear()
        append_event(
            self.state,
            EventType.SHERIFF_ELECTION_STARTED,
            visibility=EventVisibility.PUBLIC,
            payload={"round": self.state.round_no},
        )

    def set_sheriff_candidates(self, candidate_ids: tuple[str, ...]) -> None:
        """登记本局警上玩家。"""
        require_phase(self.state, Phase.SHERIFF_ELECTION)
        candidates = tuple(
            player_id
            for player_id in candidate_ids
            if get_player(self.state, player_id).alive and get_player(self.state, player_id).can_vote
        )
        self.state.sheriff_candidate_ids = candidates
        append_event(
            self.state,
            EventType.SHERIFF_CANDIDATES_SET,
            visibility=EventVisibility.PUBLIC,
            payload={"candidate_ids": candidates},
        )

    def cast_sheriff_vote(
        self,
        voter_id: str,
        target_id: str | None,
        *,
        public_reason: str = "",
        reasoning_score: int | None = None,
    ) -> None:
        """记录一名玩家的警长竞选投票。"""
        require_phase(self.state, Phase.SHERIFF_ELECTION)
        if target_id is not None and target_id not in legal_sheriff_vote_targets(self.state, voter_id):
            raise InvalidActionError(f"非法警长投票目标：{target_id}")
        self.state.sheriff_votes[voter_id] = VoteRecord(
            voter_id=voter_id,
            target_id=target_id,
            public_reason=public_reason[:240],
            reasoning_score=reasoning_score,
        )
        append_event(
            self.state,
            EventType.SHERIFF_VOTE_RECORDED,
            visibility=EventVisibility.PUBLIC,
            actor_id=voter_id,
            payload={
                "target_id": target_id,
                "public_reason": public_reason[:240],
                "reasoning_score": reasoning_score,
            },
        )

    def resolve_sheriff_vote(self, *, final_round: bool = False) -> VoteResult:
        """结算警长竞选投票。"""
        require_phase(self.state, Phase.SHERIFF_ELECTION)
        result = resolve_vote_records(
            {voter_id: vote.target_id for voter_id, vote in self.state.sheriff_votes.items()},
            no_exile_on_tie=final_round,
        )
        append_event(
            self.state,
            EventType.SHERIFF_VOTE_RESOLVED,
            visibility=EventVisibility.PUBLIC,
            payload={
                "tally": result.tally,
                "sheriff_id": result.exiled_player_id,
                "tied_player_ids": result.tied_player_ids,
                "final_round": final_round,
            },
        )
        if result.exiled_player_id is not None:
            self.state.sheriff_id = result.exiled_player_id
            self.state.sheriff_election_done = True
            self.state.phase = Phase.DAY_SPEECH
            append_event(
                self.state,
                EventType.SHERIFF_ASSIGNED,
                visibility=EventVisibility.PUBLIC,
                actor_id=result.exiled_player_id,
                payload={"sheriff_id": result.exiled_player_id},
            )
        elif final_round:
            self.state.sheriff_badge_lost = True
            self.state.sheriff_election_done = True
            self.state.phase = Phase.DAY_SPEECH
            append_event(
                self.state,
                EventType.SHERIFF_BADGE_LOST,
                visibility=EventVisibility.PUBLIC,
                payload={"reason": "tie"},
            )
        else:
            self.state.sheriff_tied_candidate_ids = result.tied_player_ids
        self.state.sheriff_votes.clear()
        return result

    def handoff_sheriff(self, target_id: str | None) -> None:
        """警长出局时移交或撕毁警徽。"""
        if self.state.sheriff_id is None:
            return
        old_sheriff_id = self.state.sheriff_id
        if target_id is not None and get_player(self.state, target_id).alive:
            self.state.sheriff_id = target_id
            append_event(
                self.state,
                EventType.SHERIFF_HANDED_OFF,
                visibility=EventVisibility.PUBLIC,
                actor_id=old_sheriff_id,
                payload={"target_id": target_id},
            )
            return
        self.state.sheriff_id = None
        self.state.sheriff_badge_lost = True
        append_event(
            self.state,
            EventType.SHERIFF_BADGE_LOST,
            visibility=EventVisibility.PUBLIC,
            actor_id=old_sheriff_id,
            payload={"reason": "sheriff_dead"},
        )

    def werewolf_self_explode(self, actor_id: str) -> None:
        """狼人自爆，立即出局并跳过白天进入下一夜。"""
        actor = get_player(self.state, actor_id)
        if not actor.alive or actor.role is not Role.WEREWOLF:
            raise InvalidActionError("只有存活狼人可以自爆。")
        if self.state.phase not in {Phase.SHERIFF_ELECTION, Phase.DAY_SPEECH, Phase.DAY_VOTE, Phase.EXILE_PK_SPEECH, Phase.EXILE_PK_VOTE}:
            raise InvalidActionError("狼人只能在白天流程自爆。")
        was_sheriff_election = self.state.phase is Phase.SHERIFF_ELECTION
        self._kill_player(actor_id, DeathReason.SELF_EXPLODE)
        self.state.last_dead_player_ids = (actor_id,)
        append_event(
            self.state,
            EventType.WEREWOLF_SELF_EXPLODED,
            visibility=EventVisibility.PUBLIC,
            actor_id=actor_id,
            payload={"player_id": actor_id, "during_sheriff_election": was_sheriff_election},
        )
        if was_sheriff_election and not self.state.sheriff_election_done:
            self.state.sheriff_election_self_explode_count += 1
            self.state.sheriff_candidate_ids = ()
            self.state.sheriff_tied_candidate_ids = ()
            self.state.sheriff_votes.clear()
            if self.state.sheriff_election_self_explode_count >= 2:
                self.state.sheriff_badge_lost = True
                self.state.sheriff_election_done = True
                append_event(
                    self.state,
                    EventType.SHERIFF_BADGE_LOST,
                    visibility=EventVisibility.PUBLIC,
                    payload={"reason": "self_explode"},
                )
        self._check_and_set_winner()
        if not self.state.is_over:
            self.start_next_round()

    def record_speech(self, actor_id: str, speech: str, *, turn_key: str = "") -> None:
        """记录一条白天公开发言。"""
        if self.state.phase not in {
            Phase.DAY_SPEECH,
            Phase.EXILE_PK_SPEECH,
            Phase.SHERIFF_ELECTION,
        }:
            raise InvalidActionError("当前阶段不能发言。")
        player = get_player(self.state, actor_id)
        if not player.can_speak:
            raise InvalidActionError("该玩家不能发言。")
        append_event(
            self.state,
            EventType.SPEECH_RECORDED,
            visibility=EventVisibility.PUBLIC,
            actor_id=actor_id,
            payload={
                "speech": speech[:240],
                **({"turn_key": turn_key} if turn_key else {}),
            },
        )

    def start_vote(self) -> None:
        """从白天发言阶段切换到投票阶段。"""
        require_phase(self.state, Phase.DAY_SPEECH)
        self.state.phase = Phase.DAY_VOTE
        self.state.votes.clear()

    def start_pk_vote(self, tied_player_ids: tuple[str, ...]) -> None:
        """进入放逐 PK 投票阶段。"""
        self.state.pk_tied_player_ids = tied_player_ids
        self.state.phase = Phase.EXILE_PK_VOTE
        self.state.votes.clear()
        append_event(
            self.state,
            EventType.PK_STARTED,
            visibility=EventVisibility.PUBLIC,
            payload={"tied_player_ids": tied_player_ids},
        )

    def cast_vote(
        self,
        voter_id: str,
        target_id: str | None,
        *,
        public_reason: str = "",
        reasoning_score: int | None = None,
    ) -> None:
        """记录一名玩家的白天放逐投票。"""
        if self.state.phase not in {Phase.DAY_VOTE, Phase.EXILE_PK_VOTE}:
            raise InvalidActionError("当前阶段不能投票。")
        candidates = self.state.pk_tied_player_ids if self.state.phase is Phase.EXILE_PK_VOTE else None
        if self.state.phase is Phase.EXILE_PK_VOTE and voter_id in self.state.pk_tied_player_ids:
            raise InvalidActionError("PK 玩家不能参与 PK 投票。")
        validate_vote(self.state, voter_id=voter_id, target_id=target_id, candidates=candidates)
        weight = 1.5 if voter_id == self.state.sheriff_id else 1.0
        self.state.votes[voter_id] = VoteRecord(
            voter_id=voter_id,
            target_id=target_id,
            weight=weight,
            public_reason=public_reason[:240],
            reasoning_score=reasoning_score,
        )
        append_event(
            self.state,
            EventType.VOTE_RECORDED,
            visibility=EventVisibility.PUBLIC,
            actor_id=voter_id,
            payload={
                "target_id": target_id,
                "weight": weight,
                "public_reason": public_reason[:240],
                "reasoning_score": reasoning_score,
            },
        )

    def resolve_vote(self, *, is_pk: bool = False) -> VoteResult:
        """结算白天投票，PK 再平票时无人出局。"""
        if self.state.phase not in {Phase.DAY_VOTE, Phase.EXILE_PK_VOTE}:
            raise InvalidActionError("当前阶段不能结算投票。")
        result = resolve_vote_records(
            {voter_id: vote.target_id for voter_id, vote in self.state.votes.items()},
            weights={voter_id: vote.weight for voter_id, vote in self.state.votes.items()},
            no_exile_on_tie=is_pk,
        )
        if result.exiled_player_id is not None:
            self._kill_player(result.exiled_player_id, DeathReason.EXILE)
            self.state.last_exiled_player_id = result.exiled_player_id
        else:
            self.state.last_exiled_player_id = None
        self.state.vote_history.append(result)
        append_event(
            self.state,
            EventType.VOTE_RESOLVED,
            visibility=EventVisibility.PUBLIC,
            payload={
                "tally": result.tally,
                "exiled_player_id": result.exiled_player_id,
                "tied_player_ids": result.tied_player_ids,
                "is_pk": is_pk,
                "no_exile": result.no_exile,
            },
        )
        if result.no_exile:
            append_event(
                self.state,
                EventType.NO_EXILE,
                visibility=EventVisibility.PUBLIC,
                payload={"reason": "tie" if result.tied_player_ids else "no_vote"},
            )
        self._check_and_set_winner()
        return result

    def start_next_round(self) -> None:
        """如果游戏未结束，进入下一轮夜晚。"""
        if self.state.phase is Phase.GAME_OVER:
            return
        self.state.round_no += 1
        self.state.phase = Phase.NIGHT
        self.state.night_actions = NightActionBuffer()
        self.state.votes.clear()
        self.state.sheriff_votes.clear()
        self.state.pk_tied_player_ids = ()
        self.state.last_dead_player_ids = ()
        self.state.last_exiled_player_id = None
        append_event(
            self.state,
            EventType.NEXT_ROUND_STARTED,
            visibility=EventVisibility.PUBLIC,
            payload={"round": self.state.round_no},
        )
        append_event(
            self.state,
            EventType.NIGHT_STARTED,
            visibility=EventVisibility.PUBLIC,
            payload={"round": self.state.round_no},
        )

    def living_role(self, role: Role) -> str | None:
        """返回指定角色的存活玩家 id。"""
        player = find_role_player(self.state, role)
        if player and player.alive:
            return player.player_id
        return None

    def _kill_player(self, player_id: str, reason: DeathReason) -> None:
        """把玩家标记为出局并记录死亡原因。"""
        player = get_player(self.state, player_id)
        if not player.alive:
            return
        player.alive = False
        player.can_vote = False
        player.dead_reason = reason

    def _check_and_set_winner(self) -> Winner | None:
        """检查胜负，并在有胜者时把游戏状态改为结束。"""
        winner = check_winner(self.state)
        append_event(
            self.state,
            EventType.WIN_CHECKED,
            visibility=EventVisibility.PUBLIC,
            payload={"winner": winner.value if winner else None},
        )
        if winner is not None:
            self.state.winner = winner
            self.state.phase = Phase.GAME_OVER
        return winner
