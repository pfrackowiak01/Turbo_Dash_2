from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import stable_baselines3
import torch
from stable_baselines3 import PPO

from .callbacks import PipelineCallback
from .manifest import create_manifest, write_json
from .paths import DEFAULT_CONFIG, DEFAULT_WORKER, RUNS_ROOT, SEED_ROOT
from .protocol import ActionSpace
from .seeds import TrainingSeedScheduler, load_seed_split
from .vec_env import TurboDashVecEnv
from .worker import start_workers


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train PPO against Turbo Dash Unity workers")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--worker-exe", type=Path, default=DEFAULT_WORKER)
    parser.add_argument("--run-id")
    parser.add_argument("--workers", type=int)
    parser.add_argument("--time-scale", type=float)
    parser.add_argument("--timesteps", type=int, help="Target total environment transitions")
    parser.add_argument("--experiment-seed", type=int)
    parser.add_argument("--checkpoint-interval", type=int)
    parser.add_argument("--validation-interval", type=int)
    parser.add_argument("--validation-workers", type=int)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--scheduler-state", type=Path)
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--purpose", choices=("training", "smoke"), default="training")
    return parser.parse_args()


def load_config(args: argparse.Namespace) -> dict:
    config = json.loads(args.config.read_text(encoding="utf-8"))
    overrides = {
        "workers": args.workers,
        "time_scale": args.time_scale,
        "total_timesteps": args.timesteps,
        "experiment_seed": args.experiment_seed,
        "checkpoint_interval": args.checkpoint_interval,
        "validation_interval": args.validation_interval,
        "validation_workers": args.validation_workers,
    }
    for key, value in overrides.items():
        if value is not None:
            config[key] = value
    if config.get("algorithm") != "PPO":
        raise ValueError("This entry point supports PPO only")
    config["action_space"] = ActionSpace.from_name(config.get("action_space", "")).name.title()
    if config.get("normalize_observation") or config.get("normalize_reward"):
        raise ValueError("PPO Pilot v1 does not normalize observations or rewards")
    for key in ("workers", "total_timesteps", "checkpoint_interval", "validation_interval", "validation_workers"):
        if int(config[key]) <= 0:
            raise ValueError(f"{key} must be positive")
    if float(config["time_scale"]) <= 0:
        raise ValueError("time_scale must be positive")
    return config


def policy_digest(model: PPO) -> str:
    digest = hashlib.sha256()
    for name, tensor in sorted(model.policy.state_dict().items()):
        digest.update(name.encode("utf-8"))
        digest.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return digest.hexdigest()


def infer_scheduler_path(checkpoint: Path) -> Path:
    stem = checkpoint.stem
    if not stem.startswith("ppo_"):
        raise ValueError("Cannot infer scheduler state: checkpoint name must start with ppo_")
    return checkpoint.with_name("seed_scheduler_" + stem[4:] + ".json")


def main() -> int:
    args = parse_args()
    config = load_config(args)
    action_space = ActionSpace.from_name(config["action_space"])
    if stable_baselines3.__version__ != "2.9.0":
        raise RuntimeError(f"stable-baselines3 2.9.0 is required, found {stable_baselines3.__version__}")
    worker_exe = args.worker_exe.resolve()
    if not worker_exe.is_file():
        raise FileNotFoundError(f"Research Worker build is missing: {worker_exe}")
    train_path = SEED_ROOT / "train.json"
    validation_path = SEED_ROOT / "validation.json"
    train_seeds = load_seed_split(train_path, "train")
    validation_seeds = load_seed_split(validation_path, "validation")
    action_name = config["action_space"].lower()
    run_id = args.run_id or datetime.now(timezone.utc).strftime(f"ppo-{action_name}-%Y%m%d-%H%M%S")
    run_dir = RUNS_ROOT / run_id
    if run_dir.exists():
        raise FileExistsError(f"Run directory already exists: {run_dir}")
    manifest = create_manifest(
        config, allow_dirty=args.allow_dirty, run_id=run_id, purpose=args.purpose,
        worker_executable=worker_exe, parent_checkpoint=str(args.resume.resolve()) if args.resume else None,
    )
    for child in ("tensorboard", "checkpoints", "best_model", "validation", "worker_logs", "unity_episode_csv"):
        (run_dir / child).mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "config.json", config)
    write_json(run_dir / "manifest.json", manifest)
    scheduler = TrainingSeedScheduler(train_seeds, int(config["experiment_seed"]))
    workers = []
    env = None
    model = None
    started = time.perf_counter()
    try:
        workers = start_workers(
            int(config["workers"]), worker_exe, run_dir,
            time_scale=float(config["time_scale"]), action_space=action_space, nographics=True,
        )
        env = TurboDashVecEnv(workers, scheduler)
        policy_kwargs = {
            "activation_fn": torch.nn.Tanh,
            "net_arch": config["policy_kwargs"]["net_arch"],
        }
        if args.resume:
            scheduler_path = args.scheduler_state or infer_scheduler_path(args.resume)
            scheduler.load(scheduler_path.resolve())
            model = PPO.load(args.resume.resolve(), env=env, device="cpu")
            model.tensorboard_log = str((run_dir / "tensorboard").resolve())
            initial_steps = int(model.num_timesteps)
        else:
            model = PPO(
                config["policy"], env,
                learning_rate=float(config["learning_rate"]),
                gamma=float(config["gamma"]),
                gae_lambda=float(config["gae_lambda"]),
                clip_range=float(config["clip_range"]),
                ent_coef=float(config["ent_coef"]),
                vf_coef=float(config["vf_coef"]),
                max_grad_norm=float(config["max_grad_norm"]),
                n_steps=int(config["n_steps"]),
                batch_size=int(config["batch_size"]),
                n_epochs=int(config["n_epochs"]),
                policy_kwargs=policy_kwargs,
                tensorboard_log=str((run_dir / "tensorboard").resolve()),
                seed=int(config["experiment_seed"]),
                device="cpu",
                verbose=1,
            )
            initial_steps = 0
        initial_digest = policy_digest(model)
        target_steps = int(config["total_timesteps"])
        remaining = target_steps - initial_steps
        if remaining <= 0:
            raise ValueError(f"Target {target_steps} does not exceed checkpoint timesteps {initial_steps}")
        callback = PipelineCallback(
            run_dir, scheduler, worker_exe, validation_seeds,
            checkpoint_interval=int(config["checkpoint_interval"]),
            validation_interval=int(config["validation_interval"]),
            validation_workers=int(config["validation_workers"]),
            time_scale=float(config["time_scale"]),
            action_space=action_space,
        )
        callback.align_with_existing_steps(initial_steps)
        model.learn(total_timesteps=remaining, callback=callback, reset_num_timesteps=not bool(args.resume),
                    tb_log_name="PPO_Pilot_v1")
        final_steps = int(model.num_timesteps)
        final_path = callback.save_checkpoint(f"final_{final_steps}")
        loaded = PPO.load(final_path, device="cpu")
        if int(loaded.num_timesteps) != final_steps:
            raise RuntimeError("Saved checkpoint did not preserve total timesteps")
        final_digest = policy_digest(model)
        event_files = list((run_dir / "tensorboard").rglob("events.out.tfevents.*"))
        if not event_files:
            raise RuntimeError("TensorBoard did not create an event file")
        env.close()
        env = None
        workers = []
        manifest.update({
            "status": "complete",
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            "result": {
                "initial_timesteps": initial_steps,
                "total_timesteps": final_steps,
                "wall_seconds": time.perf_counter() - started,
                "transitions_per_second": (final_steps - initial_steps) / (time.perf_counter() - started),
                "initial_policy_sha256": initial_digest,
                "final_policy_sha256": final_digest,
                "weights_updated": initial_digest != final_digest,
                "checkpoint": str(final_path.resolve()),
                "checkpoint_load_verified": True,
                "tensorboard_event_files": [str(path.resolve()) for path in event_files],
                "finite_observations_rewards_and_logged_losses": True,
                "test_status": "UNUSED FOR TRAINING/TUNING/EVALUATION",
            },
        })
        if not args.resume and not manifest["result"]["weights_updated"]:
            raise RuntimeError("PPO policy weights did not change")
        write_json(run_dir / "manifest.json", manifest)
        print(json.dumps(manifest["result"], indent=2))
        return 0
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        write_json(run_dir / "manifest.json", manifest)
        raise
    finally:
        for worker in workers:
            worker.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
