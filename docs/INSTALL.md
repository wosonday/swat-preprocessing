# Cài đặt SWATprep (không cần Docker)

Dành cho người dùng trong nhóm. Chỉ cần làm **một lần**; sau đó mở app bằng biểu tượng trên Desktop.

## Windows

1. Tải tệp **`install.bat`** bằng link cố định (luôn là bản mới nhất):
   `https://github.com/wosonday/swat-preprocessing/releases/latest/download/install.bat`
2. Nhấp đúp `install.bat`. Nếu Windows hiện cảnh báo SmartScreen, chọn **More info → Run anyway**.
3. Chờ cửa sổ đen báo **Done** (lần đầu có thể mất vài phút vì phải tải Python và thư viện), rồi nhấn phím bất kỳ.
4. Trên Desktop xuất hiện biểu tượng **SWATprep**.

**Mỗi lần dùng:** nhấp đúp **SWATprep** → trình duyệt tự mở trang app. Để tắt app, đóng cửa sổ đen.

**Cập nhật:** nhấp đúp lại `install.bat` (bản đã tải trước đó cũng được): nó luôn cài **phiên bản mới nhất**.

**Quay về một phiên bản cũ** (ví dụ khi bản mới có lỗi): mở *Command Prompt* trong thư mục chứa `install.bat` và gõ `install.bat v0.3.0`. Danh sách các phiên bản: `https://github.com/wosonday/swat-preprocessing/releases`. Phiên bản đang dùng hiển thị ở trang **Home** của app.

## Linux / macOS

```sh
curl -LO https://github.com/wosonday/swat-preprocessing/releases/latest/download/install.sh
sh install.sh            # bản mới nhất
sh install.sh v0.3.0     # hoặc một phiên bản cụ thể
```

Sau đó mở bằng mục **SWATprep** trong menu ứng dụng (Linux), hoặc chạy lệnh in ra ở cuối.

## Dùng app

1. Mở trang **Project**.
2. Ở **Project folder**, dán đường dẫn thư mục dự án (ví dụ `D:\SWAT-model\projects\MaDa`) hoặc bấm **Browse** → chọn thư mục → **Use this folder**.
3. Chọn config ở **Open config**, hoặc tạo mới ở **New config**.
4. Bấm **Validate**, sửa các ô báo đỏ nếu có, rồi bấm **Build**.

## Khi gặp lỗi

- Trang **Home** liệt kê phiên bản và các driver GDAL; chụp màn hình trang này khi báo lỗi.
- Cài đặt thất bại: chụp màn hình cửa sổ đen gửi người quản lý SWATprep.
- Mở app hai lần: bản thứ hai tự chạy ở cổng 8502, 8503… Nên đóng cửa sổ đen cũ và chỉ giữ một bản.
- App chỉ mở được từ chính máy đang chạy nó (`localhost`); máy khác trong mạng không truy cập được.
