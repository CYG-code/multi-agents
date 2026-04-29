const legacyUsername = process.env.TEST_USERNAME
const legacyPassword = process.env.TEST_PASSWORD

export const TEST_ACCOUNTS = {
  teacher: {
    username: process.env.TEST_TEACHER_USERNAME || legacyUsername || 'laoshi_test',
    password: process.env.TEST_TEACHER_PASSWORD || legacyPassword || 'laoshi_test',
  },
  student: {
    username: process.env.TEST_STUDENT_USERNAME || 'xuesheng_test',
    password: process.env.TEST_STUDENT_PASSWORD || 'xuesheng_test',
  },
}
