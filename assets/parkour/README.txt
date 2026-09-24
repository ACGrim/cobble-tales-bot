Put 3-6 Minecraft parkour gameplay videos (MP4) in this folder before Reddit
story videos will have real footage. build_parkour_background() in
assemble_video.py picks one at random for each video, along with a random
start point, and crops it to fill the vertical frame. If this folder is
empty, Reddit-story videos still build fine -- they just get a plain
gradient background instead, which is why it's safe to leave empty until
you've sourced real footage.

Why this is a local folder and not a live API search (like assets/music/
and how career-video b-roll works): stock-footage sites (Pexels, Pixabay --
already integrated elsewhere in this pipeline) don't carry real gameplay
recordings, they're built for generic b-roll. This genre works from a small
personal library of parkour footage that gets reused across many videos, the
same way the music folder holds a handful of tracks rather than searching
for new music every run.

Where to get clips you're actually safe to reuse and monetize with, in
order of how sure you can be of the rights:

  1. Record your own (safest, AND officially sanctioned by Microsoft --
     checked their actual usage-guidelines page at minecraft.net so this
     isn't a guess). Microsoft's Minecraft Usage Guidelines explicitly
     permit monetizing your own gameplay footage on YouTube/TikTok/
     Instagram, with two real conditions: the video stays free to view (no
     paywall, no selling the clip itself), and you add "your own unique
     content" rather than just reposting raw, unedited gameplay. A Reddit-
     story video clears that bar easily -- the original narration, the
     original written story, and the captions are exactly the kind of
     substantial original content the guidelines are asking for; the
     parkour clip is the background, not the product. Play a parkour map
     for 20-30 minutes with OBS or your OS's built-in screen recorder,
     export as MP4. You now own the recording outright, forever, for any
     use. Most creators in this niche do exactly this once and reuse the
     recording for months.
  2. A licensed footage pack, bought specifically for reuse in content like
     this. Verified a concrete example while researching this: "Breeze -
     No Copyright Gameplay" on Ko-fi (ko-fi.com/s/72a41cf945) sells 4K/60fps
     Minecraft parkour clips, pay-what-you-want (min $5), and its listing
     states outright "you can monetize your content with this copyright
     free gameplay." That's a real, explicit license grant in writing --
     screenshot/save the purchase confirmation as your proof if you go this
     route. (Not a recommendation to use this specific seller over others
     -- just confirming this category of product is real and does exist,
     so it's worth shopping around for one with clear written terms.)
  3. A YouTube/TikTok video someone else uploaded and labeled "no
     copyright" or "free to use." Checked a real example of this while
     researching (a "No Copyright Gameplay"-style TikTok clip) and it
     confirms the skepticism below is warranted: its actual terms were
     "please give credit to my channel" and "don't reupload as your own"
     -- informal social-media asks, not a real copyright license, and no
     indication the uploader holds the rights to grant one anyway (a lot
     of these channels are themselves just re-recording someone else's
     parkour map). Don't treat a video's title or hashtags as a license.
     Before downloading anything, open the actual description and look for
     explicit language granting permission to download, reuse, and
     monetize the footage elsewhere. If it doesn't say that in plain
     terms, don't use it -- assume it's not actually cleared. Given #1 is
     free, sanctioned by Microsoft itself, and takes about half an hour,
     it's hard to beat -- treat this option as a last resort.

Do NOT use footage recorded by someone else without a clear, explicit grant
of reuse rights -- that's a copyright strike waiting to happen, and unlike
music, YouTube/TikTok/Instagram have no equivalent "content ID" free pass
for gameplay footage the way they do for some pre-cleared audio libraries.

Keep individual files comfortably under 100MB -- GitHub blocks any single
file over that outright, and large binary files bloat the repo either way.
A 10-15 minute 1080p H.264 recording at a moderate bitrate (720p is plenty
for a background layer that's mostly obscured by captions/text anyway)
fits well under that. 3-6 clips gives enough variety that the same footage
isn't immediately recognizable across every post.
