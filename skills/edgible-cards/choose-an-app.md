# Choose an app

Part of the edgible-cards skill: read [SKILL.md](SKILL.md) first.

Use this step only when the person described a need and no card meets it, or when the app they named is unsuitable. Do not pick from memory. Shortlist from [awesome-selfhosted](https://awesome-selfhosted.net), a curated list of free self-hosted software, through its machine-readable data. That data has one YAML file per app, with its categories (`tags`), platforms, licence, stars, last update, and whether it is archived.

```bash
ash=$(mktemp -d)
curl -fsSL https://github.com/awesome-selfhosted/awesome-selfhosted-data/archive/refs/heads/master.tar.gz \
  | tar -xz --strip-components=1 -C "$ash"
ls "$ash/tags"    # the categories; the needs map names the category for the needs it covers
```

Then list that category's apps, with each one's description, most starred first:

```bash
tag="Bookmarks and Link Sharing"   # the name: line of the category's file in tags/
for f in $(grep -l -- "- $tag\$" "$ash"/software/*.yml); do
  awk -v app="$(basename "$f" .yml)" '
    /^stargazers_count:/ {stars = $2}
    /^updated_at:/       {updated = $2}
    /^  - Docker$/       {docker = "docker"}
    /^archived: true/    {note = note " archived"}
    /^depends_3rdparty: true/ {note = note " needs-3rd-party"}
    /^description:/      {sub(/^description: /, ""); desc = $0}
    END {printf "%s\t%s\t%s\t%s\t%s\t%s\n", stars, app, updated, (docker ? docker : "-"), note, desc}' "$f"
done | sort -rn | head -25
```

**Rank by how well an app does the job, not by stars.** Stars measure popularity, and a popular app in the category may do a different job: for "members book our tennis courts", the most-starred Booking and Scheduling apps book appointments with a person or hotel rooms, and the right one, a resource-booking app, has a small fraction of their stars. Read each app's `description` against the person's job, and use stars only to choose between apps that fit equally well.

**AI tools.** awesome-selfhosted covers few of them. When the entry has `find`, shortlist from those sources as well, with the same rules. Two that cover most AI needs:

```bash
# MCP servers: the official registry. Servers with packages run on your own machine.
curl -fsS "https://registry.modelcontextprotocol.io/v0/servers?search=postgres&version=latest&limit=50" \
  | python3 -c '
import json, sys
for entry in json.load(sys.stdin)["servers"]:
    s = entry["server"]
    if s.get("packages"):
        print(s["name"], (s.get("repository") or {}).get("url") or "-", s.get("description"), sep="\t")
'
# Other AI tools: GitHub topics, most starred, updated recently
gh api "search/repositories?q=topic:vector-database+pushed:>$(date -v-6m +%F 2>/dev/null || date -d '6 months ago' +%F)&sort=stars&per_page=15" \
  --jq '.items[] | [.stargazers_count, .full_name, .description] | @tsv'
```

The registry does not rank or review servers, and many are near-copies. Prefer one from the maker of the tool it connects to, then one whose repository is active and well used, and read what its tools can do before offering it. Most packaged servers speak `stdio` (the registry's `transport`), which only a local client can use: the `mcp-bridge` app card serves it over Streamable HTTP.

Keep only apps that list `Docker`, are not archived, were updated within about six months, and do not need a third-party service. Read the shortlisted apps' own docs for what the list does not say: the containers and database they need, how the first admin is made, and whether they have phone or desktop apps. Apps with their own clients need an auth mode other than `org` on some hostname: see the cards README's auth table.

Offer two or three candidates in one message. For each, give what it is best at and what it costs to run: containers, database, memory, and the auth trade-off. Recommend one and say why, and let the person choose. A simple app that meets the need usually beats the one with the most features.
