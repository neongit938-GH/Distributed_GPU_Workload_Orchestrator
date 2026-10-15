# Fairlane: NFS Shared Storage

This folder documents how Fairlane's shared storage is set up with NFS (Network File System). Every machine in the system (worker nodes and user machines) sees the same files through it, so we never have to write our own file-transfer code.

**Track owner:** Harshvardhan Sharma
**Tested on:** Ubuntu 24.04 LTS

---

## Why NFS?

A training job is submitted with only a *path* to a script, not the script file itself. The worker that runs the job has to be able to open that path, and the job's log has to end up somewhere the dashboard can read. NFS makes one folder on a server look like a normal local folder on every other machine:

- **Users** put their scripts and data into their own folder on the share.
- **Workers** read the script from the share and write the log back to it.
- **The dashboard** reads the log straight from the share.

This is the same pattern used in Slurm-style GPU clusters (see NVIDIA DeepOps in the references).

---

## Design decisions

| Decision | Value | Why |
|---|---|---|
| Server export path | `/srv/fairlane` | `/srv` is the standard Linux location for data a machine serves to others. It also keeps the server folder separate from the mount point, which matters when the server is also a client. |
| Client mount point | `/mnt/shared_jobs` (same on every machine) | Every machine sees the share at the same path, so a relative path means the same thing everywhere. |
| Paths stored by the scheduler | Relative to the mount, e.g. `users/alice/job_1/train.py` | The scheduler never depends on where the share is mounted. |
| Export options | `rw,sync,no_subtree_check` | Read-write. `sync` writes to disk before confirming, which is safe if the server crashes. `no_subtree_check` is recommended by the exports man page. |
| `root_squash` | On (the default) | A client's root user is treated as `nobody` on the share, so having `sudo` on a laptop doesn't give root over the shared files. |
| Identity | Numeric UIDs must match on every machine | NFS identifies users by UID number, not username. If UIDs differ, permissions break without any warning. |
| Isolation (planned, step 3) | Each user folder owned by `user:compute_workers`, mode `750` | The owner has full access, workers can read and enter, and other users have no access. |

### Folder layout

```
/srv/fairlane/                  (server)  ==  /mnt/shared_jobs/  (every client)
└── users/
    └── <username>/
        ├── myenv/              optional user environment
        └── job_<id>/
            ├── train.py        the user's script
            └── log.txt         written by the worker
```

### Known limitation

Plain NFS trusts the UID a client claims. Someone with root on their own machine could create a local user with another person's UID and read that person's files. Fixing this needs Kerberized NFSv4, which is out of scope. **We assume a trusted lab network.**

---

## Progress

### Step 1: server and loopback mount on one machine

The goal is to learn exports, mounts, `root_squash` and UID behavior on a single machine before involving the network.

- [x] **Part A**: install the NFS server
- [x] **Part B**: create the export folder
- [ ] **Part C**: add the export rule and apply it
- [ ] **Part D**: mount the share as a client (loopback)
- [ ] **Part E**: experiment 1, a file appears on both sides
- [ ] **Part F**: experiment 2, `root_squash` blocks `sudo`
- [ ] **Part G**: experiment 3, ownership is tracked by UID number
- [ ] **Part H**: unmount and clean up

### Upcoming

- [ ] **Step 2**: real server and client over the network, firewall rule, permanent mount via `/etc/fstab`
- [ ] **Step 3**: UID matching across machines, the `compute_workers` group, 750 permissions on user folders
- [ ] **Step 4**: Docker check. A container started with `-v /mnt/shared_jobs:/mnt/shared_jobs` reads a user's script and writes its log, and the 750 model still works for the user ID inside the container.

---

## Step 1 procedure

All commands run in a normal terminal. PyCharm's terminal works too. Paths beginning with `/` are absolute, so the current folder doesn't matter.

### Part A: install the NFS server ✅

```bash
sudo apt update
sudo apt install nfs-kernel-server
```

This installs the server and also `nfs-common` (the client tools), so one machine can act as both server and client.

Check that it's running:

```bash
systemctl status nfs-server
```

Expected: `Active: active (exited)`. "exited" is normal, because NFS runs inside the kernel and the service only starts it. If it says `inactive`, run `sudo systemctl enable --now nfs-server`.

### Part B: create the export folder ✅

```bash
sudo mkdir -p /srv/fairlane/users
ls -ld /srv/fairlane
```

Expected:

```
drwxr-xr-x 3 root root 4096 ... /srv/fairlane
```

The folder is owned by root with mode 755. This matters in Part F.

> `/srv` isn't a hidden folder. The Files app opens your home folder by default, so press **Ctrl+L** and type `/srv/fairlane` to browse to it.

### Part C: add the export rule and apply it

```bash
echo '/srv/fairlane 127.0.0.1(rw,sync,no_subtree_check)' | sudo tee -a /etc/exports
cat /etc/exports        # the line should appear exactly ONCE at the bottom
sudo exportfs -ra       # re-read /etc/exports and apply it (no output = success)
sudo exportfs -v        # show the active exports
```

Expected `exportfs -v` output:

```
/srv/fairlane  127.0.0.1(sync,wdelay,hide,no_subtree_check,sec=sys,rw,secure,root_squash,no_all_squash)
```

Notes:
- `127.0.0.1` means only this machine may mount the share for now. In step 2 it becomes the lab subnet, e.g. `192.168.1.0/24`.
- Use `sudo tee -a`, not `>>`. `>>` runs without root and fails, because `/etc/exports` is owned by root.
- Don't edit `/etc/exports` in an IDE. Use `sudo nano /etc/exports`.

### Part D: mount the share as a client

```bash
sudo mkdir -p /mnt/shared_jobs
sudo mount -t nfs 127.0.0.1:/srv/fairlane /mnt/shared_jobs
findmnt /mnt/shared_jobs
```

Expected: `SOURCE 127.0.0.1:/srv/fairlane`, `FSTYPE nfs4`, with `vers=4.2` in the options.

### Part E: a file appears on both sides

```bash
echo "hello from server side" | sudo tee /srv/fairlane/hello.txt
cat /mnt/shared_jobs/hello.txt
```

Expected: `hello from server side`. It's one file seen through two paths. On a real worker, only the `/mnt/shared_jobs` path exists.

### Part F: `root_squash` blocks `sudo`

```bash
sudo touch /mnt/shared_jobs/root_test.txt
```

Expected: `Permission denied`, even with `sudo`.

**Why:** the request goes through NFS, and `root_squash` turns the client's root into `nobody` on the server. `/srv/fairlane` is owned by root with mode 755, so only its owner can write to it, and `nobody` isn't the owner.

### Part G: ownership is tracked by UID number

```bash
id                                                  # note your uid (usually 1000)
sudo mkdir /srv/fairlane/users/$USER                # server side: local root isn't squashed
sudo chown $USER:$USER /srv/fairlane/users/$USER
touch /mnt/shared_jobs/users/$USER/train.py         # through the mount, no sudo: works
ls -l  /mnt/shared_jobs/users/$USER/                # owner shown as a name
ls -ln /mnt/shared_jobs/users/$USER/                # owner shown as the number NFS actually uses
```

**Takeaway:** NFS stores and checks the number. If another machine had a *different* user with the same UID, NFS would treat them as the same person. That's why step 3 makes UIDs consistent across machines.

### Part H: clean up

```bash
sudo umount /mnt/shared_jobs
findmnt /mnt/shared_jobs        # no output = unmounted
```

This mount isn't permanent and disappears on reboot. Making it permanent with `/etc/fstab` is part of step 2. Files in `/srv/fairlane` are kept.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `mount` hangs | NFS server isn't running | Ctrl+C, then `sudo systemctl enable --now nfs-server` |
| `access denied by server while mounting` | The client isn't allowed in `/etc/exports`, or the change wasn't applied | Check the line in `/etc/exports`, then `sudo exportfs -ra` |
| `exportfs` warns about duplicate entries | The export line was added twice | Remove the duplicate with `sudo nano /etc/exports` |
| `Permission denied` when using `sudo` on the mount | `root_squash` (expected behavior) | Do admin work on the server path `/srv/fairlane`, not through the mount |
| Files show the wrong owner on another machine | UIDs don't match between machines | Covered in step 3 |

---

## References

- `exports(5)` man page, "General Options" and "User ID Mapping": https://man7.org/linux/man-pages/man5/exports.5.html
- Ubuntu Server, NFS: https://documentation.ubuntu.com/server/network-file-system-nfs/
- Linux kernel NFS admin guide: https://docs.kernel.org/admin-guide/nfs/index.html
- NVIDIA DeepOps, Slurm with NFS: https://github.com/NVIDIA/deepops/blob/master/docs/slurm-cluster/slurm-nfs.md
