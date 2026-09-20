import { invoke, isTauri } from '@tauri-apps/api/core';

export interface CourseSummary { id: string; title: string; lessonCount: number }
export interface Lesson {
  id: string; title: string; objective: string; language: string; code: string;
  explanation: string; syntax: string; rationale: string; exercise: string; reflection: string;
  contentType: 'project-brief' | 'concept' | 'implementation' | 'verification';
  practiceTask?: { prompt: string; requiredFiles: string[]; acceptance: string[] };
}
export interface Course { id: string; title: string; lessons: Lesson[] }
export const foundationCourse: Course = {
  id: 'trainer-foundations-javascript', title: 'JavaScript 编程基础', lessons: [
    { id:'reading', title:'代码是什么', objective:'认识值、名字，以及一行代码表达的动作。', language:'JavaScript', code:'let name = "小明";', explanation:'这句话的意思是：把“小明”这段文字记下来，并给它贴上 name 这个标签。', syntax:'let 表示新建一个名字；name 是标签；等号右侧是要保存的值。', rationale:'程序需要稳定的名字，后续步骤才能找到并使用同一份信息。', exercise:'指出 name 和“小明”分别承担什么角色，再预测把文字改成“小红”会发生什么。', reflection:'请用自己的话解释：为什么名字不是值本身？', contentType:'concept' },
    { id:'values', title:'值与变量', objective:'区分稳定的名字与会变化的值。', language:'JavaScript', code:'let score = 18;\nscore = score + 1;', explanation:'先记住 18，再把它更新为 19。名字 score 没变，它所指向的值变了。', syntax:'右侧先读取并计算，等号再把结果交给左侧名字。', rationale:'分数、余额和库存都会变化，变量让程序追踪当前状态。', exercise:'逐行写出 score 的值，并说明第二行为什么不能倒过来读。', reflection:'什么情况下应该使用会变化的变量？', contentType:'concept' },
    { id:'conditions', title:'条件判断', objective:'让程序在不同情况选择不同路径。', language:'JavaScript', code:'if (score >= 60) {\n  console.log("通过");\n}', explanation:'只有分数达到 60 时，程序才会输出“通过”。', syntax:'if 后面是得到真或假的判断；大括号包含条件成立时执行的步骤。', rationale:'权限、库存和登录状态都需要条件选择。', exercise:'分别代入 59 和 60，写出程序是否会输出。', reflection:'边界值 60 为什么值得单独检查？', contentType:'concept' },
    { id:'functions', title:'函数：把步骤命名', objective:'把重复步骤命名并按需调用。', language:'JavaScript', code:'function greet(name) {\n  console.log("你好", name);\n}\ngreet("小明");', explanation:'先定义“打招呼”这件事，再把“小明”交给它完成。', syntax:'函数名是步骤入口，括号里的 name 接收每次调用的数据。', rationale:'集中重复逻辑，规则变化时只修改一个地方。', exercise:'把“小明”换成“小红”，指出定义和调用分别在哪里。', reflection:'函数和普通变量最大的区别是什么？', contentType:'concept' },
    { id:'types', title:'类型：信息的种类', objective:'认识文字、数字和真假。', language:'JavaScript', code:'const name = "小明";\nconst age = 18;\nconst isMember = true;', explanation:'名字是文字，年龄是数字，会员资格只有是或否。', syntax:'引号表示文字；18 是数字；true 是布尔值。', rationale:'类型决定信息可以参与哪些操作，并帮助发现错误。', exercise:'为三个值标注类型，再判断 age + 1 是否合理。', reflection:'为什么不能把所有信息都当作文字？', contentType:'concept' },
    { id:'projects', title:'读懂一个小项目', objective:'按入口、数据、规则、输出建立项目地图。', language:'JavaScript', code:'function main() {\n  const score = 18;\n  console.log(score);\n}\nmain();', explanation:'从 main 开始：准备数据，执行规则，最后展示结果。', syntax:'入口函数把流程串起来；局部变量只服务于这一次运行。', rationale:'先建立地图再读细节，不会被大量文件淹没。', exercise:'按执行顺序标出三步，并找出真正启动程序的那一行。', reflection:'面对陌生项目时，你会先找什么？', contentType:'concept' }
  ]
};
type RecordValue = Record<string, unknown>;
function record(value: unknown): value is RecordValue {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}
function nonempty(value: unknown): value is string { return typeof value === 'string' && value.trim().length > 0; }
function planID(value: unknown): value is string { return typeof value === 'string' && /^[a-f0-9]{64}$/.test(value); }
function incompatible(): never { throw new Error('课程格式不兼容，请更新本地服务后重试。'); }
function requireDesktop() {
  if (!isTauri()) throw new Error('浏览器仅提供界面预览。请在桌面客户端打开本机已保存课程。');
}
export async function loadCourses(): Promise<CourseSummary[]> {
  requireDesktop();
  const value: unknown = await invoke('courses');
  if (!record(value) || !Array.isArray(value.courses) || value.courses.length > 1000) incompatible();
  const seen = new Set<string>();
  return value.courses.map((item: unknown) => {
    if (!record(item) || !planID(item.id) || !nonempty(item.title)
      || typeof item.lessonCount !== 'number' || !Number.isSafeInteger(item.lessonCount)
      || item.lessonCount < 1 || seen.has(item.id)) incompatible();
    seen.add(item.id);
    return { id: item.id, title: item.title, lessonCount: item.lessonCount };
  });
}
export async function loadCourse(planId: string): Promise<Course> {
  if (planId === foundationCourse.id) return foundationCourse;
  requireDesktop();
  if (!planID(planId)) throw new Error('课程编号无效，请重新选择课程。');
  const value: unknown = await invoke('course', { planId });
  if (!record(value) || value.id !== planId || !nonempty(value.title)
    || !Array.isArray(value.lessons) || !value.lessons.length) incompatible();
  const fields = ['id', 'title', 'objective', 'language', 'code', 'explanation', 'syntax', 'rationale', 'exercise', 'reflection'] as const;
  const seen = new Set<string>();
  for (const item of value.lessons) {
    if (!record(item) || fields.some(field => !nonempty(item[field]))
      || !['project-brief', 'concept', 'implementation', 'verification'].includes(String(item.contentType))
      || seen.has(String(item.id))) incompatible();
    seen.add(String(item.id));
    if (item.practiceTask !== undefined) {
      const task = item.practiceTask;
      if (!record(task) || !nonempty(task.prompt) || !Array.isArray(task.requiredFiles)
        || !task.requiredFiles.length || !task.requiredFiles.every(nonempty)
        || !Array.isArray(task.acceptance) || !task.acceptance.length || !task.acceptance.every(nonempty)) incompatible();
    }
  }
  return value as unknown as Course;
}
