from collections import deque

from stable_baselines3.common.callbacks import BaseCallback


class TrainingMetricsCallback(BaseCallback):
    def __init__(self, log_every: int = 1, rolling_window: int = 50, verbose: int = 1):
        super().__init__(verbose)
        self.log_every = log_every
        self.rolling_window = rolling_window
        self.episode_count = 0
        self.episode_reward = 0.0
        self.episode_changed_count = 0
        self.episode_action_failed_count = 0
        self.rewards = deque(maxlen=rolling_window)
        self.recovered_flags = deque(maxlen=rolling_window)
        self.ttr_values = deque(maxlen=rolling_window)
        self.availability_values = deque(maxlen=rolling_window)

    def _on_step(self) -> bool:
        infos = self.locals.get("infos", [])
        dones = self.locals.get("dones", [])
        rewards = self.locals.get("rewards", [])
        for i, done in enumerate(dones):
            self.episode_reward += float(rewards[i])
            info = infos[i]
            if info.get("changed", False):
                self.episode_changed_count += 1
            if info.get("action_failed", False):
                self.episode_action_failed_count += 1
            if done:
                self.episode_count += 1
                recovered = info.get("recovered", False)
                ttr = info.get("recovery_time_s")
                avail = info.get("availability", 0.0)
                self.rewards.append(self.episode_reward)
                self.recovered_flags.append(int(recovered))
                if ttr is not None:
                    self.ttr_values.append(float(ttr))
                self.availability_values.append(float(avail))
                if self.episode_count % self.log_every == 0:
                    ttr_str = f"{ttr:.1f}" if ttr is not None else "-"
                    print(f"[ep {self.episode_count}] steps={self.num_timesteps} "
                          f"reward={self.episode_reward:.2f} recovered={int(recovered)} "
                          f"ttr={ttr_str} avail={avail:.2f} "
                          f"changed={self.episode_changed_count} "
                          f"failed={self.episode_action_failed_count}")
                self.logger.record("train/episode_reward", self.episode_reward)
                self.logger.record("train/recovered", int(recovered))
                if ttr is not None:
                    self.logger.record("train/ttr", float(ttr))
                self.logger.record("train/availability", avail)
                self.logger.record("train/changed_count", self.episode_changed_count)
                self.logger.record("train/action_failed_count", self.episode_action_failed_count)
                if self.recovered_flags:
                    self.logger.record("train/recovery_rate_50ep",
                                        sum(self.recovered_flags) / len(self.recovered_flags))
                if self.ttr_values:
                    self.logger.record("train/ttr_mean_50ep",
                                        sum(self.ttr_values) / len(self.ttr_values))
                if self.availability_values:
                    self.logger.record("train/avail_mean_50ep",
                                        sum(self.availability_values) / len(self.availability_values))
                if self.rewards:
                    self.logger.record("train/reward_mean_50ep",
                                        sum(self.rewards) / len(self.rewards))
                self.logger.dump(step=self.num_timesteps)
                self.episode_reward = 0.0
                self.episode_changed_count = 0
                self.episode_action_failed_count = 0
        return True