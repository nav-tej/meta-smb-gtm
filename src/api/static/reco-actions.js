// Home page "Improve" list: 1:1 insight preview thumbnails, moves-done strip,
// and rich ad preview dialog with placement switching, competitor compare view, and export.
// Device-local, zero model calls.
(function () {
  'use strict';
  var ACTIONS_KEY = 'muse.actions';

  var DEFAULT_PREVIEWS = [
    {
      insight_id: 'idea-1-empowering-women',
      source: 'ranked_idea',
      placement: 'instagram_feed',
      headline: 'Sikh Women of Strength — Mai Bhago & Kaur Legacy',
      caption: 'While mainstream Sikh art galleries feature warrior heroes, our Empowering Women series honors the courage, devotion, and leadership of Sikh women across history. Archival museum-grade prints starting at $18. Tap to discover the full collection on Pixels.',
      cta: 'Explore series',
      image_ref: '/samples/naam_japo_restored_gallery_live.webp',
      evidence: [
        { label: 'SikhiArt has warrior and saint groups but none for women', url: 'https://www.sikhiart.com/', kind: 'sample' },
        { label: 'Sarabjit catalog has dedicated Mai Bhago and Kaur empowerment collection', url: null, kind: 'sample' }
      ],
      why_this: 'SikhiArt has 8 shop collections for warriors and saints, but zero for women. Lead with your unique collection.',
      checklist: [
        'Share Mai Bhago painting with caption on Instagram',
        'Pin link to Empowering Women Pixels collection in bio',
        'Offer 10% off for holiday gift sets'
      ],
      competitor_card: {
        name: 'SikhiArt',
        format: 'Shop collection',
        primary_text: 'Sells warrior heroes (Baba Deep Singh, Hari Singh Nalwa) from $59.99 to $2,499. No women collection.',
        price_point: '$59.99 - $2,499.99',
        url: 'https://www.sikhiart.com',
        note: '[sample] Based on SikhiArt crawl (Nov 3)'
      }
    },
    {
      insight_id: 'idea-2-starter-prints',
      source: 'ranked_idea',
      placement: 'instagram_feed',
      headline: 'Timeless Sikh Heritage Art from $14',
      caption: 'Museum-grade fine art shouldn’t require a $100+ commitment. Start your art wall with authentic archival prints on luster paper, beginning at just $14. Handcrafted with reverence.',
      cta: 'Shop prints from $14',
      image_ref: '/samples/ek_onkar_collector_room_live.webp',
      evidence: [
        { label: 'SikhiArt entry price starts at $59.99', url: 'https://www.sikhiart.com/', kind: 'sample' },
        { label: 'Pixels marketplace prints start at $14–$22', url: 'https://pixels.com/', kind: 'sample' }
      ],
      why_this: '3 of 4 competitors start at $60+. Leading with $14 prints wins gift and first-time buyers.',
      checklist: [
        'Feature $14 print option prominently in caption',
        'Add direct link to $14 luster print variant',
        'Highlight free US delivery on orders over $50'
      ],
      competitor_card: {
        name: 'SikhiArt',
        format: 'Print catalog',
        primary_text: 'Cheapest open edition print is $59.99. No starter prints under $50.',
        price_point: 'From $59.99',
        url: 'https://www.sikhiart.com',
        note: '[sample] SikhiArt catalog analysis'
      }
    },
    {
      insight_id: 'idea-3-gift-ready',
      source: 'ranked_idea',
      placement: 'instagram_feed',
      headline: 'The Thoughtful Spiritual Gift That Lasts a Lifetime',
      caption: 'Looking for a meaningful housewarming, wedding, or Gurpurab gift? A fine art print of the Golden Temple brings peace and timeless reflection into any home. Custom gift notes available with every order.',
      cta: 'Send as a gift',
      image_ref: '/samples/golden_temple_holiday_gift_live.webp',
      evidence: [
        { label: 'SikhiArt uses gift wording but has nothing under $59.99', url: 'https://www.sikhiart.com/', kind: 'sample' },
        { label: 'Desi Canvas Co targets wedding & housewarming gifts at $129', url: null, kind: 'sample' }
      ],
      why_this: 'Competitors use gift seasonal wording but charge $60–$129+. You can offer curated $20–$50 gifts.',
      checklist: [
        'Add gift-note offer to checkout instructions',
        'Post Golden Temple print mockup in home setting',
        'Tag as #sikhgift #spiritualdecor'
      ],
      competitor_card: {
        name: 'Desi Canvas Co',
        format: 'Meta feed ad',
        primary_text: 'Transform your living room for Gurpurab & Diwali. Ready-to-hang museum-grade canvas prints starting at $129.',
        price_point: 'From $129.00',
        url: null,
        note: '[sample] Meta Ad Library capture'
      }
    },
    {
      insight_id: 'idea-4-home-titles',
      source: 'ranked_idea',
      placement: 'facebook_feed',
      headline: 'Listing Optimization: \'For Your Home\' Decor Titles',
      caption: 'Search visibility update for your shop: Add \'for your home\' to high-intent titles to capture buyers searching for sacred decor rather than generic paintings.',
      cta: 'Update listings',
      image_ref: '/samples/kirat_karo_collector_room_live.webp',
      evidence: [
        { label: 'Almost every SikhiArt product title includes \'for Your Home by Bhagat Singh Bedi\'', url: 'https://www.sikhiart.com/', kind: 'sample' }
      ],
      why_this: 'SikhiArt adds \'for Your Home\' to almost every title to rank in Google & Etsy home decor searches.',
      checklist: [
        'Listing 1: Change \'Ek Onkar Painting\' to \'Ek Onkar Sacred Sikh Art Print for Your Home\'',
        'Listing 2: Change \'Golden Temple Watercolor\' to \'Harmandir Sahib Golden Temple Fine Art for Your Home\'',
        'Listing 3: Change \'Mai Bhago Artwork\' to \'Mai Bhago Warrior Heritage Canvas Print for Your Home\''
      ],
      competitor_card: {
        name: 'SikhiArt',
        format: 'SEO / Catalog pattern',
        primary_text: 'Example: \'Golden Temple in Moonlight Painting for Your Home by Bhagat Singh Bedi\'',
        price_point: 'SEO standard',
        url: 'https://www.sikhiart.com',
        note: '[sample] Product title strategy analysis'
      }
    },
    {
      insight_id: 'idea-5-painting-story',
      source: 'ranked_idea',
      placement: 'instagram_feed',
      headline: 'The Story Behind Ek Onkar: One Infinite Creator',
      caption: 'Behind every brushstroke is a meditation on unity. When I painted this Ek Onkar piece, I wanted the sacred symbol to emerge from quiet gold and deep crimson — a daily reminder that the Divine dwells in all creation. What feeling does it bring to your quiet space?',
      cta: 'Read the story',
      image_ref: '/samples/diptych_ek_onkar_kirat_karo_live.webp',
      evidence: [
        { label: 'SikhiArt has only 2 blog pages and no artist stories', url: 'https://www.sikhiart.com/', kind: 'sample' }
      ],
      why_this: 'Competitors post impersonal product specs. A five-sentence story behind the art builds true emotional connection.',
      checklist: [
        'Post Ek Onkar painting with personal reflection',
        'Ask question in caption to drive comments and saves',
        'Add link to artist statement on website'
      ],
      competitor_card: {
        name: 'SikhiArt',
        format: 'Blog & Social',
        primary_text: 'Only 2 blog pages total. Zero artist process or spiritual storytelling posts.',
        price_point: 'Content gap',
        url: 'https://www.sikhiart.com',
        note: '[sample] Content cadence audit'
      }
    }
  ];

  function readActions() {
    try {
      var v = JSON.parse(localStorage.getItem(ACTIONS_KEY) || '{}');
      return v && typeof v === 'object' ? v : {};
    } catch (_) {
      return {};
    }
  }

  function track(name, props) {
    try {
      if (typeof window.museTrack === 'function') {
        window.museTrack(name, props);
      } else if (window.posthog && window.posthog.capture) {
        window.posthog.capture(name, props);
      }
    } catch (_) {}
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text) node.textContent = text;
    return node;
  }

  // --- Modal Dialog Singleton ---
  var dialogEl = null;
  var currentSpec = null;
  var currentPlacement = 'instagram_feed';
  var isComparing = false;

  function ensureDialog() {
    if (dialogEl) return dialogEl;

    dialogEl = el('dialog', 'jr-preview-dialog');
    dialogEl.id = 'jrPreviewModal';
    dialogEl.setAttribute('aria-labelledby', 'jrDialogTitle');

    var wrap = el('div', 'jr-preview-wrap');

    // Header
    var head = el('div', 'jr-dialog-head');
    var title = el('h3', '', 'Idea preview');
    title.id = 'jrDialogTitle';
    var closeBtn = el('button', 'jr-close-btn', '×');
    closeBtn.type = 'button';
    closeBtn.setAttribute('aria-label', 'Close preview dialog');
    closeBtn.addEventListener('click', function () {
      dialogEl.close();
    });
    head.appendChild(title);
    head.appendChild(closeBtn);
    wrap.appendChild(head);

    // Body
    var body = el('div', 'jr-dialog-body');

    // Why this badge
    var whyBadge = el('div', 'jr-why-badge');
    whyBadge.id = 'jrWhyBadge';
    body.appendChild(whyBadge);

    // Placement switcher & compare toggle
    var placeBar = el('div', 'jr-placement-bar');
    placeBar.appendChild(el('span', '', 'Format:'));

    var btnFeed = el('button', 'jr-placement-btn active', 'Instagram 4:5');
    btnFeed.type = 'button';
    btnFeed.dataset.placement = 'instagram_feed';

    var btnStory = el('button', 'jr-placement-btn', 'Story 9:16');
    btnStory.type = 'button';
    btnStory.dataset.placement = 'instagram_story';

    var btnFb = el('button', 'jr-placement-btn', 'Facebook feed');
    btnFb.type = 'button';
    btnFb.dataset.placement = 'facebook_feed';

    var compareBtn = el('button', 'jr-compare-toggle-btn', 'Compare with competitor pattern');
    compareBtn.type = 'button';
    compareBtn.id = 'jrCompareBtn';

    placeBar.appendChild(btnFeed);
    placeBar.appendChild(btnStory);
    placeBar.appendChild(btnFb);
    placeBar.appendChild(compareBtn);
    body.appendChild(placeBar);

    // Preview grid
    var grid = el('div', 'jr-preview-grid');
    grid.id = 'jrPreviewGrid';

    // Post frame
    var postFrame = el('div', 'jr-post-frame');
    postFrame.id = 'jrPostFrame';

    var postHead = el('div', 'jr-post-header');
    var avatar = el('div', 'jr-post-avatar', 'M');
    avatar.id = 'jrPostAvatar';
    var postMeta = el('div', 'jr-post-meta');
    var postHandle = el('span', 'jr-post-handle', '@artofsarabjit');
    postHandle.id = 'jrPostHandle';
    var postTag = el('span', 'jr-post-tag', 'Sponsored · [sample]');
    postMeta.appendChild(postHandle);
    postMeta.appendChild(postTag);
    postHead.appendChild(avatar);
    postHead.appendChild(postMeta);

    var mediaBox = el('div', 'jr-post-media jr-aspect-4-5');
    mediaBox.id = 'jrMediaBox';
    var postImg = el('img');
    postImg.id = 'jrPostImg';
    postImg.alt = 'Ad preview image';
    mediaBox.appendChild(postImg);

    var postContent = el('div', 'jr-post-content');
    var postHeadline = el('h4', 'jr-post-headline');
    postHeadline.id = 'jrPostHeadline';
    var postCaption = el('p', 'jr-post-caption');
    postCaption.id = 'jrPostCaption';
    var postCtaBar = el('div', 'jr-post-cta-bar');
    var postCtaBtn = el('button', 'jr-post-cta-btn', 'Shop now');
    postCtaBtn.type = 'button';
    postCtaBtn.id = 'jrPostCtaBtn';
    postCtaBar.appendChild(postCtaBtn);

    postContent.appendChild(postHeadline);
    postContent.appendChild(postCaption);
    postContent.appendChild(postCtaBar);

    postFrame.appendChild(postHead);
    postFrame.appendChild(mediaBox);
    postFrame.appendChild(postContent);

    // Checklist Card (for non-post moves)
    var checklistCard = el('div', 'jr-checklist-card');
    checklistCard.id = 'jrChecklistCard';
    checklistCard.hidden = true;
    var checkHead = el('h4', '', 'Step-by-step listing update checklist');
    var checkList = el('ul', 'jr-checklist-items');
    checkList.id = 'jrChecklistItems';
    checklistCard.appendChild(checkHead);
    checklistCard.appendChild(checkList);

    // Competitor Card (for compare view)
    var compFrame = el('div', 'jr-competitor-frame');
    compFrame.id = 'jrCompFrame';
    compFrame.hidden = true;

    grid.appendChild(postFrame);
    grid.appendChild(checklistCard);
    grid.appendChild(compFrame);
    body.appendChild(grid);
    wrap.appendChild(body);

    // Action bar
    var actions = el('div', 'jr-dialog-actions');
    var copyBtn = el('button', 'jr-btn-secondary', 'Copy caption');
    copyBtn.type = 'button';
    copyBtn.id = 'jrCopyCaptionBtn';

    var downloadPngBtn = el('button', 'jr-btn-primary', 'Download PNG');
    downloadPngBtn.type = 'button';
    downloadPngBtn.id = 'jrDownloadPngBtn';

    var downloadTxtBtn = el('button', 'jr-btn-secondary', 'Download instructions (.txt)');
    downloadTxtBtn.type = 'button';
    downloadTxtBtn.id = 'jrDownloadTxtBtn';

    var openCreatorLink = el('a', 'jr-btn-link', 'Open in Creator Studio →');
    openCreatorLink.id = 'jrOpenCreatorLink';
    openCreatorLink.href = '/create';

    actions.appendChild(copyBtn);
    actions.appendChild(downloadPngBtn);
    actions.appendChild(downloadTxtBtn);
    actions.appendChild(openCreatorLink);
    wrap.appendChild(actions);

    dialogEl.appendChild(wrap);
    document.body.appendChild(dialogEl);

    // Wire listeners
    var placeBtns = [btnFeed, btnStory, btnFb];
    placeBtns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        placeBtns.forEach(function (b) { b.classList.remove('active'); });
        btn.classList.add('active');
        switchPlacement(btn.dataset.placement);
      });
    });

    compareBtn.addEventListener('click', function () {
      toggleCompare();
    });

    copyBtn.addEventListener('click', function () {
      if (!currentSpec) return;
      var textToCopy = currentSpec.caption || '';
      if (currentSpec.checklist && currentSpec.checklist.length) {
        textToCopy += '\n\nAction Checklist:\n' + currentSpec.checklist.map(function (c, i) { return (i + 1) + '. ' + c; }).join('\n');
      }
      copyToClipboard(textToCopy, copyBtn, 'Caption copied!');
      track('reco_caption_copied', { reco_id: currentSpec.insight_id });
    });

    downloadPngBtn.addEventListener('click', function () {
      if (!currentSpec) return;
      downloadPreviewPng(currentSpec, currentPlacement);
      track('reco_preview_downloaded', { reco_id: currentSpec.insight_id, format: 'png', placement: currentPlacement });
    });

    downloadTxtBtn.addEventListener('click', function () {
      if (!currentSpec) return;
      downloadInstructionsTxt(currentSpec);
      track('reco_preview_downloaded', { reco_id: currentSpec.insight_id, format: 'txt' });
    });

    return dialogEl;
  }

  function switchPlacement(placement) {
    currentPlacement = placement;
    var mediaBox = document.getElementById('jrMediaBox');
    if (!mediaBox) return;

    mediaBox.classList.remove('jr-aspect-4-5', 'jr-aspect-9-16', 'jr-aspect-fb');
    if (placement === 'instagram_story') {
      mediaBox.classList.add('jr-aspect-9-16');
    } else if (placement === 'facebook_feed') {
      mediaBox.classList.add('jr-aspect-fb');
    } else {
      mediaBox.classList.add('jr-aspect-4-5');
    }

    if (currentSpec) {
      track('reco_placement_switched', { reco_id: currentSpec.insight_id, placement: placement });
    }
  }

  function toggleCompare(force) {
    var compFrame = document.getElementById('jrCompFrame');
    var grid = document.getElementById('jrPreviewGrid');
    var compBtn = document.getElementById('jrCompareBtn');
    if (!compFrame || !grid || !compBtn) return;

    isComparing = typeof force === 'boolean' ? force : !isComparing;
    compFrame.hidden = !isComparing;
    if (isComparing) {
      grid.classList.add('comparing');
      compBtn.classList.add('active');
    } else {
      grid.classList.remove('comparing');
      compBtn.classList.remove('active');
    }

    if (currentSpec) {
      track('reco_compare_toggled', { reco_id: currentSpec.insight_id, shown: isComparing });
    }
  }

  function openPreview(spec, ideaTitle, rank) {
    currentSpec = spec;
    ensureDialog();

    var title = document.getElementById('jrDialogTitle');
    if (title) title.textContent = ideaTitle || spec.headline || 'Idea preview';

    var why = document.getElementById('jrWhyBadge');
    if (why) {
      why.textContent = '';
      var strong = el('strong', '', 'Why this:');
      why.appendChild(strong);
      why.appendChild(document.createTextNode(' ' + (spec.why_this || 'Based on competitor gaps in your niche.') + ' [sample]'));
    }

    // Get current shop handle
    var shopName = 'Art of Sarabjit Singh';
    try {
      var activeLabel = document.getElementById('activeWorkspaceLabel');
      if (activeLabel && activeLabel.textContent.trim()) {
        shopName = activeLabel.textContent.trim();
      }
    } catch (_) {}
    var handleText = '@' + shopName.toLowerCase().replace(/[^a-z0-9]+/g, '');
    var avatarChar = (shopName.charAt(0) || 'M').toUpperCase();

    var avatar = document.getElementById('jrPostAvatar');
    if (avatar) avatar.textContent = avatarChar;
    var handle = document.getElementById('jrPostHandle');
    if (handle) handle.textContent = handleText;

    var postImg = document.getElementById('jrPostImg');
    if (postImg) postImg.src = spec.image_ref || '/samples/ek_onkar_collector_room_live.webp';

    var postHeadline = document.getElementById('jrPostHeadline');
    if (postHeadline) postHeadline.textContent = spec.headline || '';

    var postCaption = document.getElementById('jrPostCaption');
    if (postCaption) postCaption.textContent = spec.caption || '';

    var postCtaBtn = document.getElementById('jrPostCtaBtn');
    if (postCtaBtn) postCtaBtn.textContent = spec.cta || 'Shop now';

    // Checklist handling for non-post moves
    var checklistCard = document.getElementById('jrChecklistCard');
    var postFrame = document.getElementById('jrPostFrame');
    if (spec.checklist && spec.checklist.length) {
      if (checklistCard) {
        checklistCard.hidden = false;
        var checkList = document.getElementById('jrChecklistItems');
        if (checkList) {
          checkList.textContent = '';
          spec.checklist.forEach(function (item) {
            var li = el('li');
            var icon = el('span', 'jr-check-icon', '✓');
            var txt = el('span', '', item);
            li.appendChild(icon);
            li.appendChild(txt);
            checkList.appendChild(li);
          });
        }
      }
    } else {
      if (checklistCard) checklistCard.hidden = true;
    }

    // Competitor Card
    var compFrame = document.getElementById('jrCompFrame');
    if (compFrame && spec.competitor_card) {
      compFrame.textContent = '';
      var cHead = el('div', 'jr-comp-header');
      cHead.appendChild(el('strong', '', spec.competitor_card.name || 'Competitor pattern'));
      cHead.appendChild(el('span', 'jr-comp-tag', spec.competitor_card.format || 'Ad / Catalog'));

      var cBody = el('div', 'jr-comp-body', spec.competitor_card.primary_text || '');
      var cPrice = el('div', 'jr-comp-price', 'Competitor pricing: ' + (spec.competitor_card.price_point || 'N/A'));
      var cContrast = el('div', 'jr-comp-contrast', 'Your opening: ' + (spec.why_this || 'Under-cut entry pricing or fill missing collection.'));
      var cNote = el('div', 'jr-comp-note', spec.competitor_card.note || '[sample] Competitor research finding');

      compFrame.appendChild(cHead);
      compFrame.appendChild(cPrice);
      compFrame.appendChild(cBody);
      compFrame.appendChild(cContrast);
      compFrame.appendChild(cNote);
    }

    // Default compare to false on fresh open
    toggleCompare(false);

    // Reset placement to feed
    switchPlacement('instagram_feed');
    var placeBtns = dialogEl.querySelectorAll('.jr-placement-btn');
    placeBtns.forEach(function (b) {
      if (b.dataset.placement === 'instagram_feed') b.classList.add('active');
      else b.classList.remove('active');
    });

    var creatorLink = document.getElementById('jrOpenCreatorLink');
    if (creatorLink) {
      creatorLink.href = '/create?goal=' + encodeURIComponent(spec.insight_id);
    }

    dialogEl.showModal();
    track('reco_preview_open', { reco_id: spec.insight_id, rank: rank || 1, placement: currentPlacement });
  }

  function copyToClipboard(text, btn, feedbackText) {
    var original = btn.textContent;
    var done = function () {
      btn.textContent = feedbackText || 'Copied!';
      setTimeout(function () { btn.textContent = original; }, 2000);
    };

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(function () {
        fallbackCopy(text);
        done();
      });
    } else {
      fallbackCopy(text);
      done();
    }
  }

  function fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch (_) {}
    document.body.removeChild(ta);
  }

  function downloadPreviewPng(spec, placement) {
    var canvas = document.createElement('canvas');
    var w = 1080;
    var h = 1350;
    if (placement === 'instagram_story') {
      w = 1080; h = 1920;
    } else if (placement === 'facebook_feed') {
      w = 1200; h = 630;
    }
    canvas.width = w;
    canvas.height = h;
    var ctx = canvas.getContext('2d');
    if (!ctx) return;

    var img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = function () {
      // Background fill
      ctx.fillStyle = '#141413';
      ctx.fillRect(0, 0, w, h);

      // Draw image to fill aspect ratio
      var imgAspect = img.width / img.height;
      var canvasAspect = w / h;
      var drawW = w;
      var drawH = h;
      var offsetX = 0;
      var offsetY = 0;

      if (imgAspect > canvasAspect) {
        drawW = h * imgAspect;
        offsetX = (w - drawW) / 2;
      } else {
        drawH = w / imgAspect;
        offsetY = (h - drawH) / 2;
      }
      ctx.drawImage(img, offsetX, offsetY, drawW, drawH);

      // Bottom gradient scrim
      var gradient = ctx.createLinearGradient(0, h - 360, 0, h);
      gradient.addColorStop(0, 'rgba(0,0,0,0)');
      gradient.addColorStop(0.5, 'rgba(0,0,0,0.65)');
      gradient.addColorStop(1, 'rgba(0,0,0,0.9)');
      ctx.fillStyle = gradient;
      ctx.fillRect(0, h - 360, w, 360);

      // Headline
      ctx.fillStyle = '#ffffff';
      ctx.font = 'bold 44px -apple-system, BlinkMacSystemFont, "Inter", sans-serif';
      var text = spec.headline || '';
      ctx.fillText(text.slice(0, 48), 54, h - 140);

      // CTA bar
      ctx.fillStyle = '#2f6f4f';
      ctx.beginPath();
      ctx.roundRect ? ctx.roundRect(54, h - 90, 260, 60, 10) : ctx.fillRect(54, h - 90, 260, 60);
      ctx.fill();

      ctx.fillStyle = '#ffffff';
      ctx.font = 'bold 26px -apple-system, BlinkMacSystemFont, "Inter", sans-serif';
      ctx.fillText(spec.cta || 'Shop now', 85, h - 50);

      // Convert to blob and download
      canvas.toBlob(function (blob) {
        if (!blob) return;
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = (spec.insight_id || 'preview') + '-' + placement + '.png';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
      }, 'image/png');
    };
    img.src = spec.image_ref || '/samples/ek_onkar_collector_room_live.webp';
  }

  function downloadInstructionsTxt(spec) {
    var lines = [
      'MUSE CREATIVE SPEC & POSTING PLAN',
      '==================================',
      'Insight ID: ' + spec.insight_id,
      'Headline: ' + spec.headline,
      'CTA: ' + spec.cta,
      'Recommended Placement: ' + spec.placement,
      '',
      'CAPTION TO COPY:',
      '----------------------------------',
      spec.caption,
      '',
      'WHY THIS MOVE:',
      '----------------------------------',
      spec.why_this,
      ''
    ];

    if (spec.checklist && spec.checklist.length) {
      lines.push('ACTION CHECKLIST:');
      lines.push('----------------------------------');
      spec.checklist.forEach(function (step, i) {
        lines.push((i + 1) + '. ' + step);
      });
      lines.push('');
    }

    if (spec.competitor_card) {
      lines.push('COMPETITOR EVIDENCE & GAP:');
      lines.push('----------------------------------');
      lines.push('Competitor: ' + spec.competitor_card.name);
      lines.push('Their price: ' + spec.competitor_card.price_point);
      lines.push('Their ad/post: ' + spec.competitor_card.primary_text);
      lines.push('Finding: ' + spec.competitor_card.note);
      lines.push('');
    }

    lines.push('Generated by Muse Growth Studio [sample demo]. No remote model calls.');

    var blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = (spec.insight_id || 'preview') + '-posting-instructions.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  // --- Main Init ---
  async function init() {
    var list = document.querySelector('#loop-improve .jr-recos');
    if (!list || list.dataset.recoReady) return;
    list.dataset.recoReady = '1';
    var items = Array.prototype.slice.call(list.children);

    // Moves-done Progress Strip
    var strip = el('div', 'jr-moves');
    strip.setAttribute('role', 'status');
    var stripText = el('strong');
    var bar = el('div', 'jr-moves-bar');
    var fill = el('span');
    bar.appendChild(fill);
    var stripNote = el('small');
    strip.appendChild(stripText);
    strip.appendChild(bar);
    strip.appendChild(stripNote);
    list.parentNode.insertBefore(strip, list);

    function refreshStrip() {
      var all = readActions();
      var done = 0, todo = 0, aside = 0;
      items.forEach(function (li) {
        var rec = all[li.dataset.actionId];
        var status = rec && rec.status;
        if (status === 'done') done += 1;
        else if (status === 'accepted') todo += 1;
        else if (status === 'dismissed' || status === 'archived') aside += 1;
      });
      var open = items.length - aside;
      stripText.textContent = done + ' of ' + open + ' moves done' +
        (todo ? ' · ' + todo + ' on your to-do list' : '') +
        (aside ? ' · ' + aside + ' set aside' : '');
      fill.style.width = (open ? Math.round((done / open) * 100) : 0) + '%';
      stripNote.textContent = done || todo
        ? 'Saved on this device. Mark a move done in My actions once you have posted it.'
        : 'Accept an idea to start tracking. Saved on this device.';
    }
    refreshStrip();

    list.addEventListener('click', function () { setTimeout(refreshStrip, 60); });
    document.addEventListener('click', function (event) {
      if (event.target && event.target.closest && event.target.closest('.ms-drawer, .ms-actions, dialog')) {
        setTimeout(refreshStrip, 60);
      }
    });
    window.addEventListener('storage', function (event) { if (event.key === ACTIONS_KEY) refreshStrip(); });
    window.addEventListener('focus', refreshStrip);

    // Load 1:1 previews (from /api/v1/previews with DEFAULT_PREVIEWS fallback)
    var previews = DEFAULT_PREVIEWS;
    try {
      var resp = await fetch('/api/v1/previews');
      if (resp.ok) {
        var data = await resp.json();
        if (Array.isArray(data.previews) && data.previews.length > 0) {
          previews = data.previews;
        }
      }
    } catch (_) {}

    // Attach 1:1 Thumbnails to every idea item
    items.forEach(function (li, index) {
      if (li.querySelector('.jr-reco-thumb')) return;
      var spec = previews[index % previews.length];
      var ideaHead = li.querySelector('strong');
      var ideaTitle = (ideaHead ? ideaHead.textContent : '').trim() || spec.headline;

      var btn = el('button', 'jr-reco-thumb');
      btn.type = 'button';
      btn.dataset.insightId = spec.insight_id;
      btn.setAttribute('aria-label', 'Preview 1:1 ad for ' + ideaTitle);

      if (spec.image_ref && !spec.checklist?.length) {
        var img = document.createElement('img');
        img.src = spec.image_ref;
        img.alt = '';
        img.loading = 'lazy';
        btn.appendChild(img);
        btn.appendChild(el('span', '', 'Preview post'));
      } else if (spec.image_ref) {
        var img2 = document.createElement('img');
        img2.src = spec.image_ref;
        img2.alt = '';
        img2.loading = 'lazy';
        btn.appendChild(img2);
        btn.appendChild(el('span', '', 'Checklist'));
      } else {
        var placeholder = el('div', 'jr-thumb-placeholder');
        placeholder.appendChild(el('div', '', '📋'));
        placeholder.appendChild(el('span', '', 'Checklist'));
        btn.appendChild(placeholder);
        btn.appendChild(el('span', '', 'Checklist'));
      }

      btn.addEventListener('click', function (event) {
        event.stopPropagation();
        openPreview(spec, ideaTitle, index + 1);
      });

      li.classList.add('has-thumb');
      li.appendChild(btn);
    });

    refreshStrip();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
