export const ratingQuestionnaire = {
  notice: "按正式对打或比赛中通常能做到的情况选择，以平时发挥为准。",
  quick_levels: [
    { value: 2.0, name: "初学", description: "正在练习找准击球点和基本击球动作，对单打、双打站位还不熟悉。" },
    { value: 2.5, name: "入门", description: "能和同水平球友在底线慢速对拉几个回合，来球判断、移动和回位还不够稳定。" },
    { value: 3.0, name: "稳定对拉", description: "回击中速球较稳定，但控制方向、深浅和球速的准确性有限，网前击球还不够熟练。" },
    { value: 4.0, name: "进阶", description: "中速对抗中，正反手都能控制方向和深浅，能有效使用挑高球、随球上网、截击和高压，双打配合较明确。" },
  ],
};

export const NTRP_QUESTIONS = [
  {
    id: "experience",
    title: "打球经历",
    options: [
      { label: "刚接触，不到 3 个月", score: 1 },
      { label: "学过几个月，能简单对拉", score: 2 },
      { label: "打了 1–2 年，每周都打", score: 3 },
      { label: "3 年以上，经常参加比赛", score: 4 },
      { label: "校队或专业训练背景", score: 5 },
    ],
  },
  {
    id: "forehand",
    title: "正手",
    options: [
      { label: "经常打不到或控制不住", score: 1.5 },
      { label: "慢速球能打回去，方向很难控制", score: 2 },
      { label: "中速球能稳定对拉，开始控制方向", score: 3 },
      { label: "能稳定控制方向和深度，会打上旋", score: 3.5 },
      { label: "有攻击性，能主动拿分", score: 4.5 },
      { label: "是武器，深度、角度、旋转都能随心控制", score: 5.5 },
    ],
  },
  {
    id: "backhand",
    title: "反手",
    options: [
      { label: "尽量躲开反手", score: 1.5 },
      { label: "能把慢球挡回去", score: 2 },
      { label: "中速球能回过网，但打不深", score: 2.5 },
      { label: "能稳定对拉，方向有控制", score: 3.5 },
      { label: "能用反手攻击或打出削球变化", score: 4.5 },
      { label: "和正手一样可靠，能拿分", score: 5.5 },
    ],
  },
  {
    id: "serve",
    title: "发球",
    options: [
      { label: "抛球不稳，经常双误", score: 1.5 },
      { label: "能发进，但多是轻推过去", score: 2 },
      { label: "一发有节奏，二发求稳", score: 3 },
      { label: "一发有力量和落点，二发有旋转", score: 4 },
      { label: "能用发球直接得分，发球变化多", score: 5 },
    ],
  },
  {
    id: "return",
    title: "接发球",
    options: [
      { label: "经常接不到", score: 1.5 },
      { label: "慢速发球能接回", score: 2.5 },
      { label: "中速发球能稳定接回场内", score: 3 },
      { label: "能接深、接角度，偶尔主动进攻", score: 4 },
      { label: "能针对一发 / 二发做出攻击性回球", score: 5 },
    ],
  },
  {
    id: "net",
    title: "网前截击和高压球",
    options: [
      { label: "很少上网", score: 2 },
      { label: "能截击正面的慢球", score: 3 },
      { label: "能从中场上网，处理一般的高压球", score: 3.5 },
      { label: "截击有落点，高压球稳定", score: 4.5 },
      { label: "网前手段多，能在网前终结得分", score: 5.5 },
    ],
  },
  {
    id: "tactics",
    title: "比赛与战术",
    options: [
      { label: "还不太会计分", score: 1 },
      { label: "知道规则，能打完一盘", score: 2.5 },
      { label: "会双打站位，有意识地调动对手", score: 3.5 },
      { label: "能根据对手调整战术，关键分稳定", score: 4.5 },
      { label: "比赛经验丰富，压力下能保持水平", score: 5.5 },
    ],
  },
];

export const NTRP_LEVELS: Record<string, string> = {
  "1.0": "刚开始接触网球，还在熟悉握拍和击球。",
  "1.5": "能打回一些慢速来球，但还很难连续对打。",
  "2.0": "能和同水平球友慢速对拉几个回合，发球、反手、网前都还不稳定。",
  "2.5": "能维持慢速对拉，开始判断来球方向，但还打不出想要的力量和落点；会打双打的基本站位。",
  "3.0": "中速来球比较稳定，正手开始能控制方向；双打能在底线和网前站位，但打快球、深球时容易失误。",
  "3.5": "中速球的方向和深度控制明显变好，开始用旋转，能主动上网截击；比赛中会有意识地打对手弱点。",
  "4.0": "正反手都能稳定控制方向和深度，一发有力量、二发有旋转；能在对拉中组织进攻，双打配合默契。",
  "4.5": "有能拿分的武器（如正手或发球），能用力量和旋转打乱对手；失误主要来自压力下的过度发力。",
  "5.0": "击球质量高且稳定，能根据对手调整战术，有比赛经验，常参加地区级业余比赛。",
  "5.5": "以力量、稳定性和战术取胜，比赛经验丰富，接近高水平业余或有专业训练背景。",
};

export function assessQuestionnaire(answers: Record<string, number>) {
  const scores: number[] = [];
  for (const { id, options } of NTRP_QUESTIONS) {
    const selected = options.find(option => option.score === answers[id]);
    if (!selected) return null;
    scores.push(selected.score);
  }

  const average = scores.reduce((sum, score) => sum + score, 0) / scores.length;
  const weakestScore = Math.min(...scores);
  const weakestTitle = NTRP_QUESTIONS[scores.indexOf(weakestScore)].title;
  const cap = weakestScore + 1;
  const capped = Math.min(average, cap);
  const rating = Math.min(5.5, Math.max(1, Math.floor(2 * capped + 1e-9) / 2));

  return { rating, average, weakestScore, weakestTitle, cap, showWeaknessTip: weakestScore < rating };
}
